# engine/api/pr_review.py
"""PR review API — manual trigger, GitHub webhook handler, quality gate check."""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.engine.core.auth import get_current_user
from core.engine.core.config import settings
from core.engine.core.db import parse_rows, pool
from core.engine.core.tasks import logged_task
from core.engine.github.client import GitHubClient
from core.engine.github.diff_parser import parse_diff
from core.engine.review.config import ReviewConfig
from core.engine.review.engine import ReviewEngine
from core.engine.review.impact import PRImpactAnalyzer
from core.engine.review.judge import Judge

logger = logging.getLogger(__name__)

router = APIRouter(tags=["review"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ManualReviewRequest(BaseModel):
    pr_url: str = Field(description="GitHub PR URL")
    disciplines: list[str] | None = Field(default=None)
    post_review: bool = Field(default=False)


class ReviewResponse(BaseModel):
    pr_number: int
    title: str
    findings_count: int
    findings: list[dict]
    summary: str
    discipline_scores: dict[str, float]
    pass_quality_gate: bool
    gate_failures: list[str]
    impact: dict


class QualityGateResponse(BaseModel):
    pass_gate: bool
    discipline_scores: dict[str, float]
    gate_failures: list[str]
    findings_by_severity: dict[str, int]


class ReactionRequest(BaseModel):
    finding_index: int = Field(description="Index of the finding in the review")
    reaction: str = Field(description="Developer reaction: accepted | dismissed | modified")
    comment: str = Field(default="", description="Optional developer comment")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from GitHub webhook."""
    if not signature.startswith("sha256="):
        return False
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)


def _webhook_secret_or_fail_closed(secret: str, provider: str) -> str | None:
    """Require signed webhooks outside explicitly local development/test."""

    if secret:
        return secret
    if settings.environment not in {"development", "test"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider} webhook authentication is not configured",
        )
    return None


async def _post_review_to_github(
    gh: GitHubClient,
    owner: str,
    repo: str,
    pr_number: int,
    synthesis,
) -> None:
    """Format synthesis results and post a review comment on GitHub."""
    lines: list[str] = ["## ACE Code Review", ""]

    if synthesis.gate_failures:
        lines.append("**Quality gate: FAILED**")
        for failure in synthesis.gate_failures:
            lines.append(f"- {failure}")
    else:
        lines.append("**Quality gate: PASSED**")
    lines.append("")

    if synthesis.summary:
        lines.append(synthesis.summary)
        lines.append("")

    if synthesis.discipline_scores:
        lines.append("### Discipline Scores")
        for discipline, score in sorted(synthesis.discipline_scores.items()):
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            lines.append(f"- **{discipline}**: {bar} {score:.2f}")
        lines.append("")

    if synthesis.findings:
        lines.append(f"### Findings ({len(synthesis.findings)})")
        for i, finding in enumerate(synthesis.findings[:20]):  # cap to avoid huge reviews
            severity_tag = finding.severity.upper()
            lines.append(f"- **[{severity_tag}]** `{finding.file}:{finding.line}` — {finding.message} _(finding #{i})_")
            if finding.suggested_fix:
                lines.append(f"  - Suggestion: {finding.suggested_fix}")
        if len(synthesis.findings) > 20:
            lines.append(f"  - _(and {len(synthesis.findings) - 20} more…)_")

    lines.append("")
    lines.append("---")
    api_base = getattr(settings, "api_base_url", None) or ""
    reaction_url = (
        f"{api_base}/review/reaction/{owner}/{repo}/{pr_number}"
        if api_base
        else f"/review/reaction/{owner}/{repo}/{pr_number}"
    )
    lines.append(
        f"_ACE Review • {len(synthesis.findings)} findings across {len(synthesis.discipline_scores)} disciplines_"
    )
    lines.append(f"_To provide feedback on findings, use the [reaction API]({reaction_url})_")

    body = "\n".join(lines)
    event = "REQUEST_CHANGES" if synthesis.gate_failures else "COMMENT"
    try:
        await gh.post_review(owner, repo, pr_number, body=body, event=event)
    except Exception as exc:
        logger.warning("Failed to post review to GitHub pr=%s/%s#%s: %s", owner, repo, pr_number, exc)


async def _run_webhook_review(owner: str, repo_name: str, pr_number: int) -> None:
    """Background task: full review pipeline + persist to DB + post to GitHub."""
    gh = GitHubClient(token=settings.github_token)

    try:
        pr = await gh.fetch_pr(owner, repo_name, pr_number)

        # Post pending status
        try:
            await gh.post_commit_status(
                owner,
                repo_name,
                pr.head_sha,
                state="pending",
                description="ACE review in progress...",
            )
        except Exception:
            pass  # status posting is best-effort

        # Load per-repo config
        yaml_content = await gh.fetch_file(owner, repo_name, ".ace.yaml", ref=pr.base_branch)
        config = ReviewConfig.from_yaml(yaml_content) if yaml_content else ReviewConfig.default()

        raw_diff = await gh.fetch_diff(owner, repo_name, pr_number)
        files = parse_diff(raw_diff)

        engine = ReviewEngine()
        passes = await engine.run_passes(pr, files)

        judge = Judge()
        synthesis = await judge.synthesize(passes)

        # Re-check gate with repo-specific thresholds
        if config.gate:
            gate_result = judge.check_quality_gate(
                synthesis.findings,
                critical_threshold=config.gate.critical_threshold,
                high_threshold=config.gate.high_threshold,
            )
            synthesis = synthesis.model_copy(
                update={
                    "pass_quality_gate": gate_result.pass_quality_gate,
                    "gate_failures": gate_result.gate_failures,
                }
            )

        changed_paths = [f.path for f in files]
        analyzer = PRImpactAnalyzer()
        impact = await analyzer.full_impact(changed_paths)

        # Persist pr_review record
        async with pool.connection() as db:
            await db.query(
                """
                CREATE pr_review SET
                    owner = $owner,
                    repo = $repo,
                    pr_number = $pr_number,
                    title = $title,
                    summary = $summary,
                    findings_count = $findings_count,
                    findings = $findings,
                    discipline_scores = $discipline_scores,
                    pass_quality_gate = $pass_quality_gate,
                    gate_failures = $gate_failures,
                    findings_by_severity = $findings_by_severity,
                    impact = $impact,
                    reviewed_at = time::now()
                """,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "pr_number": pr_number,
                    "title": pr.title,
                    "summary": synthesis.summary,
                    "findings_count": len(synthesis.findings),
                    "findings": [f.model_dump() for f in synthesis.findings],
                    "discipline_scores": synthesis.discipline_scores,
                    "pass_quality_gate": synthesis.pass_quality_gate,
                    "gate_failures": synthesis.gate_failures,
                    "findings_by_severity": synthesis.findings_by_severity,
                    "impact": impact,
                },
            )

        # Post final status
        status_state = "success" if synthesis.pass_quality_gate else "failure"
        status_desc = f"{len(synthesis.findings)} findings" if synthesis.findings else "No issues found"
        try:
            await gh.post_commit_status(
                owner,
                repo_name,
                pr.head_sha,
                state=status_state,
                description=status_desc,
            )
        except Exception:
            logger.warning("Failed to post commit status")

        # Post review back to GitHub
        if settings.github_token and config.post_review:
            await _post_review_to_github(gh, owner, repo_name, pr_number, synthesis)

        # Auto-fix if critical/high findings have suggested fixes
        autofix_result: dict | None = None
        try:
            from core.engine.review.autofix import AutofixAgent

            agent = AutofixAgent(gh=gh)
            if agent.should_autofix(synthesis):
                fix_pr = await agent.run(owner, repo_name, pr_number, pr.base_branch, synthesis)
                if fix_pr:
                    autofix_result = {
                        "type": "github_pr",
                        "pr_number": fix_pr.get("number"),
                        "files_fixed": fix_pr.get("files_fixed", 0),
                    }
                    logger.info("Auto-fix PR created: %s/%s#%s", owner, repo_name, fix_pr.get("number", "?"))
        except Exception as exc:
            logger.warning("Autofix failed for %s/%s#%d: %s", owner, repo_name, pr_number, exc)

        # Auto-capture review decisions (fire-and-forget, never blocks)
        try:
            from core.engine.review.capture import capture_review_decisions

            engine_for_disciplines = ReviewEngine()
            logged_task(
                capture_review_decisions(
                    pr_title=pr.title,
                    disciplines=engine_for_disciplines.select_disciplines(files),
                    synthesis_summary=synthesis.summary,
                    findings_count=len(synthesis.findings),
                    findings_before_judge=synthesis.findings_before_judge,
                    findings_after_judge=synthesis.findings_after_judge,
                    pass_quality_gate=synthesis.pass_quality_gate,
                    gate_failures=synthesis.gate_failures,
                    discipline_scores=synthesis.discipline_scores,
                    autofix_result=autofix_result,
                    source=f"github:{owner}/{repo_name}#{pr_number}",
                ),
                label="pr_review.capture_decisions",
            )
        except Exception:
            # decision:745gfam2914vid6il7vt — silent capture failure removes the
            # audit trail; PR review completes but no decision-ledger entry exists.
            logger.warning(
                "PR review decision capture failed for %s/%s#%s — audit trail missing",
                owner,
                repo_name,
                pr_number,
                exc_info=True,
            )

    except Exception as exc:
        logger.error("Webhook review failed for %s/%s#%s: %s", owner, repo_name, pr_number, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/review/pr", response_model=ReviewResponse)
async def manual_review(body: ManualReviewRequest, user=Depends(get_current_user)):
    """Manually trigger a PR review."""
    gh = GitHubClient(token=settings.github_token)

    try:
        owner, repo_name, pr_number = GitHubClient.parse_pr_url(body.pr_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    pr = await gh.fetch_pr(owner, repo_name, pr_number)
    raw_diff = await gh.fetch_diff(owner, repo_name, pr_number)
    files = parse_diff(raw_diff)

    product_id = user.get("product", "product:default")
    engine = ReviewEngine(product_id=product_id)
    passes = await engine.run_passes(pr, files, disciplines=body.disciplines)

    judge = Judge()
    synthesis = await judge.synthesize(passes)

    changed_paths = [f.path for f in files]
    analyzer = PRImpactAnalyzer()
    impact = await analyzer.full_impact(changed_paths, product_id=product_id)

    if body.post_review and settings.github_token:
        await _post_review_to_github(gh, owner, repo_name, pr_number, synthesis)

    return ReviewResponse(
        pr_number=pr.number,
        title=pr.title,
        findings_count=len(synthesis.findings),
        findings=[f.model_dump() for f in synthesis.findings],
        summary=synthesis.summary,
        discipline_scores=synthesis.discipline_scores,
        pass_quality_gate=synthesis.pass_quality_gate,
        gate_failures=synthesis.gate_failures,
        impact=impact,
    )


@router.post("/webhooks/github", status_code=202)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
):
    """Handle GitHub webhook events. Fire-and-forget for PR events."""
    payload = await request.body()

    # Local development may exercise unsigned fixtures. Any deployable mode
    # fails closed instead of turning this global-auth exception into an
    # unauthenticated external side-effect trigger.
    webhook_secret = _webhook_secret_or_fail_closed(settings.github_webhook_secret, "GitHub")
    if webhook_secret:
        if not x_hub_signature_256:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Hub-Signature-256 header",
            )
        if not _verify_signature(payload, x_hub_signature_256, webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    event = x_github_event.lower()

    if event == "ping":
        return {"pong": True}

    if event == "pull_request":
        try:
            import json as _json

            data = _json.loads(payload)
        except Exception:
            data = {}

        action = data.get("action", "")
        if action in ("opened", "synchronize", "reopened"):
            pr_data = data.get("pull_request", {})
            repo_data = data.get("repository", {})
            pr_number = pr_data.get("number")
            repo_full = repo_data.get("full_name", "/")
            owner, _, repo_name = repo_full.partition("/")

            if pr_number and owner and repo_name:
                logged_task(_run_webhook_review(owner, repo_name, int(pr_number)), label="pr_review.github_webhook")

    return {"status": "accepted"}


@router.post("/webhooks/gitlab", status_code=202)
async def gitlab_webhook(
    request: Request,
    x_gitlab_event: str = Header(default=""),
    x_gitlab_token: str = Header(default=""),
):
    """Handle GitLab webhook events. Triggers review on MR open/update."""
    webhook_secret = _webhook_secret_or_fail_closed(settings.gitlab_webhook_secret, "GitLab")
    if webhook_secret:
        if x_gitlab_token != webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook token")

    payload = await request.body()

    if x_gitlab_event != "Merge Request Hook":
        return {"status": "ignored", "event": x_gitlab_event}

    try:
        import json as _json

        data = _json.loads(payload)
    except Exception:
        return {"status": "invalid_payload"}

    action = data.get("object_attributes", {}).get("action", "")
    if action not in ("open", "update", "reopen"):
        return {"status": "ignored", "action": action}

    mr = data.get("object_attributes", {})
    project = data.get("project", {})
    mr_iid = mr.get("iid")
    project_id = project.get("path_with_namespace", "")

    if not mr_iid or not project_id:
        raise HTTPException(status_code=400, detail="Missing MR data")

    # Determine GitLab base URL from project web_url
    web_url = project.get("web_url", "")
    base_url = "/".join(web_url.split("/")[:3]) if web_url else "https://gitlab.com"

    logged_task(_run_gitlab_webhook_review(project_id, mr_iid, base_url), label="pr_review.gitlab_webhook")

    return {"status": "review_queued", "mr": mr_iid}


async def _run_gitlab_webhook_review(project_id: str, mr_iid: int, base_url: str) -> None:
    """Background task: run review on GitLab MR."""
    try:
        from core.engine.review.providers import GitLabProvider

        provider = GitLabProvider(
            project_id=project_id,
            mr_iid=mr_iid,
            token=settings.gitlab_token,
            base_url=base_url,
        )

        pr, files = await provider.get_diff()
        if not files:
            return

        engine = ReviewEngine()
        passes = await engine.run_passes(pr, files)

        judge = Judge()
        synthesis = await judge.synthesize(passes)

        # Post review as MR note
        await provider.post_review(synthesis)

        # Post commit status
        status_state = "success" if synthesis.pass_quality_gate else "failure"
        await provider.post_status(status_state, f"{len(synthesis.findings)} findings")

        # Persist review record
        async with pool.connection() as db:
            owner = project_id.split("/")[0] if "/" in project_id else ""
            repo = project_id.split("/")[-1] if "/" in project_id else project_id
            await db.query(
                """
                CREATE pr_review SET
                    owner = $owner,
                    repo = $repo,
                    pr_number = $pr_number,
                    title = $title,
                    summary = $summary,
                    findings_count = $findings_count,
                    findings = $findings,
                    discipline_scores = $discipline_scores,
                    pass_quality_gate = $pass_quality_gate,
                    gate_failures = $gate_failures,
                    findings_by_severity = $findings_by_severity,
                    impact = {},
                    reviewed_at = time::now()
                """,
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": mr_iid,
                    "title": pr.title,
                    "summary": synthesis.summary,
                    "findings_count": len(synthesis.findings),
                    "findings": [f.model_dump() for f in synthesis.findings],
                    "discipline_scores": synthesis.discipline_scores,
                    "pass_quality_gate": synthesis.pass_quality_gate,
                    "gate_failures": synthesis.gate_failures,
                    "findings_by_severity": synthesis.findings_by_severity,
                },
            )

        # Autofix: create a fix MR via GitLab API
        try:
            from core.engine.review.autofix import AutofixAgent

            agent = AutofixAgent()
            if agent.should_autofix(synthesis):
                fixable = agent.get_fixable_findings(synthesis)
                by_file: dict[str, list] = {}
                for f in fixable:
                    by_file.setdefault(f.file, []).append(f)

                fixes: dict[str, str] = {}
                all_findings = []
                for file_path, file_findings in by_file.items():
                    # Fetch file from GitLab
                    import httpx

                    encoded = project_id.replace("/", "%2F")
                    gl_token = settings.gitlab_token
                    headers = {"PRIVATE-TOKEN": gl_token} if gl_token else {}
                    base = base_url.rstrip("/")
                    async with httpx.AsyncClient(timeout=20) as client:
                        resp = await client.get(
                            f"{base}/api/v4/projects/{encoded}/repository/files/{file_path.replace('/', '%2F')}/raw",
                            params={"ref": pr.base_branch},
                            headers=headers,
                        )
                        if resp.status_code == 200:
                            content = resp.text
                        else:
                            continue
                    fixed = await agent.generate_fix(file_findings[0], content)
                    if fixed and fixed != content:
                        fixes[file_path] = fixed
                        all_findings.extend(file_findings)

                if fixes:
                    await agent.create_fix_mr(
                        project_id=project_id,
                        base_branch=pr.base_branch,
                        mr_iid=mr_iid,
                        findings=all_findings,
                        fixes=fixes,
                        token=settings.gitlab_token,
                        base_url=base_url,
                    )
        except Exception:
            logger.warning("GitLab autofix failed (non-fatal)", exc_info=True)

        # Auto-capture review decisions (fire-and-forget, never blocks)
        try:
            from core.engine.review.capture import capture_review_decisions

            engine_for_disciplines = ReviewEngine()
            logged_task(
                capture_review_decisions(
                    pr_title=pr.title,
                    disciplines=engine_for_disciplines.select_disciplines(files),
                    synthesis_summary=synthesis.summary,
                    findings_count=len(synthesis.findings),
                    findings_before_judge=synthesis.findings_before_judge,
                    findings_after_judge=synthesis.findings_after_judge,
                    pass_quality_gate=synthesis.pass_quality_gate,
                    gate_failures=synthesis.gate_failures,
                    discipline_scores=synthesis.discipline_scores,
                    source=f"gitlab:{project_id}!{mr_iid}",
                ),
                label="pr_review.capture_decisions_gitlab",
            )
        except Exception:
            # decision:745gfam2914vid6il7vt — silent capture failure removes the
            # audit trail; MR review completes but no decision-ledger entry exists.
            logger.warning(
                "MR review decision capture failed for %s!%d — audit trail missing",
                project_id,
                mr_iid,
                exc_info=True,
            )

        logger.info(
            "GitLab review complete for %s!%d: %d findings",
            project_id,
            mr_iid,
            len(synthesis.findings),
        )
    except Exception as exc:
        logger.error(
            "GitLab webhook review failed for %s!%d: %s",
            project_id,
            mr_iid,
            exc,
            exc_info=True,
        )


@router.get("/review/gate/{owner}/{repo}/{pr_number}", response_model=QualityGateResponse)
async def quality_gate(owner: str, repo: str, pr_number: int):
    """Check the quality gate for a PR. No auth — for CI/CD use."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT
                pass_quality_gate,
                discipline_scores,
                gate_failures,
                findings_by_severity,
                reviewed_at
            FROM pr_review
            WHERE owner = $owner AND repo = $repo AND pr_number = $pr_number
            ORDER BY reviewed_at DESC
            LIMIT 1
            """,
            {"owner": owner, "repo": repo, "pr_number": pr_number},
        )
    rows = parse_rows(result)

    if not rows:
        # No review yet — pass by default
        return QualityGateResponse(
            pass_gate=True,
            discipline_scores={},
            gate_failures=[],
            findings_by_severity={},
        )

    row = rows[0]
    return QualityGateResponse(
        pass_gate=bool(row.get("pass_quality_gate", True)),
        discipline_scores=row.get("discipline_scores") or {},
        gate_failures=row.get("gate_failures") or [],
        findings_by_severity=row.get("findings_by_severity") or {},
    )


@router.post("/review/reaction/{owner}/{repo}/{pr_number}")
async def record_reaction(
    owner: str,
    repo: str,
    pr_number: int,
    body: ReactionRequest,
    user=Depends(get_current_user),
):
    """Record a developer's reaction to a review finding.

    Feeds accepted findings as positive patterns and dismissed findings
    as noise indicators into ACE's intelligence pipeline.
    """
    from core.engine.review.learning import ReviewLearner

    product_id = user.get("product", "product:default")
    learner = ReviewLearner()
    result = await learner.record_reaction(
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        finding_index=body.finding_index,
        reaction=body.reaction,
        comment=body.comment,
    )

    # Fire-and-forget: feed reaction to capture pipeline
    # Look up the finding from the stored review so we can enrich the observation
    async with pool.connection() as db:
        review_result = await db.query(
            """
            SELECT findings, reviewed_at FROM pr_review
            WHERE owner = $owner AND repo = $repo AND pr_number = $pr_number
            ORDER BY reviewed_at DESC LIMIT 1
            """,
            {"owner": owner, "repo": repo, "pr_number": pr_number},
        )
    review_rows = parse_rows(review_result)
    if review_rows:
        findings = review_rows[0].get("findings") or []
        if 0 <= body.finding_index < len(findings):
            finding = findings[body.finding_index]
            logged_task(
                learner.feed_to_capture(owner, repo, finding, body.reaction, product_id=product_id),
                label="pr_review.learner",
            )

    return {"status": "recorded", "id": str(result.get("id", ""))}


@router.post("/review/local")
async def trigger_local_review(
    repo_path: str = ".",
    base_branch: str = "main",
    force: bool = False,
    user=Depends(get_current_user),
):
    """Trigger a review of the current local branch against base."""
    from core.engine.review.watcher import check_and_review

    product_id = user.get("product", "product:default")
    result = await check_and_review(
        repo_path=repo_path,
        base_branch=base_branch,
        product_id=product_id,
        force=force,
    )

    if result is None:
        return {"status": "no_review_needed"}
    return result
