# engine/product/generation_engine.py
"""E3 — Generation Engine: graph-parameterized artifact generators.

Four generators that read the ACE code graph and produce real artifacts —
not generic templates, but outputs that know your actual stack, services,
discipline gaps, and decision rationale.

E3a — CI/CD Generator:     ace_generate_ci(target)
E3b — IaC Generator:       ace_generate_deploy(target)
E3c — Docs Generator:      ace_generate_docs(format)
E3d — Changelog Generator: ace_changelog(since_tag)

Closes:
  #3 Deployment   D+→A-
  #11 Version Control Mess  C+→A-
  #12 Testing Gap  B→A
  #14 Onboarding Impossible  B-→A
"""

from __future__ import annotations

import logging
import subprocess

from core.engine.core.db import parse_rows, pool
from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

# ── Stack detection helpers ───────────────────────────────────────────────────

_STACK_INDICATORS = {
    "python": ["*.py", "pyproject.toml", "requirements.txt", "setup.py"],
    "node": ["package.json", "*.ts", "*.tsx", "*.js"],
    "typescript": ["tsconfig.json", "*.ts"],
    "react": ["*.tsx", "*.jsx"],
    "docker": ["Dockerfile", "docker-compose.yml"],
    "terraform": ["*.tf", "*.tfvars"],
    "kubernetes": ["*.yaml", "k8s/"],
    "fastapi": ["fastapi", "uvicorn"],
    "nextjs": ["next.config.*"],
    "postgres": ["postgres", "postgresql", "psycopg"],
    "surrealdb": ["surrealdb", "surreal"],
    "redis": ["redis", "aioredis"],
}

CI_TARGETS = frozenset({"github_actions", "gitlab_ci", "circleci"})
DEPLOY_TARGETS = frozenset({"docker_compose", "railway", "coolify", "kamal"})
DOCS_FORMATS = frozenset({"mermaid", "onboarding_guide", "api_reference"})


async def _load_product_context(product_id: str) -> dict:
    """Load stack, capabilities, and gap profile from DB for LLM prompts."""
    context: dict = {
        "stack": [],
        "capabilities": [],
        "gap_profile": [],
        "top_decisions": [],
        "services": [],
    }
    try:
        async with pool.connection() as db:
            # Stack / capability signals
            cap_result = await db.query(
                """SELECT slug, title, category, priority, status
                   FROM capability
                   WHERE product = <record>$product AND status != 'deprecated'
                   ORDER BY priority ASC LIMIT 30""",
                {"product": product_id},
            )
            context["capabilities"] = parse_rows(cap_result)

            # Gap profile — disciplines below 0.7
            gap_result = await db.query(
                """SELECT dimension, math::mean(score) AS avg_score, count() AS gap_count
                   FROM capability_quality
                   WHERE product = <record>$product AND score < 0.7
                   GROUP BY dimension
                   ORDER BY avg_score ASC""",
                {"product": product_id},
            )
            context["gap_profile"] = [
                {
                    "dimension": r.get("dimension", ""),
                    "avg_score": round(float(r.get("avg_score") or 0.0), 2),
                    "gap_count": r.get("gap_count", 0),
                }
                for r in parse_rows(gap_result)
            ]

            # Recent key decisions
            dec_result = await db.query(
                """SELECT title, rationale, discipline, created_at
                   FROM decision
                   WHERE product = <record>$product
                   ORDER BY created_at DESC LIMIT 10""",
                {"product": product_id},
            )
            context["top_decisions"] = [
                {"title": r.get("title", ""), "rationale": r.get("rationale", "")[:200]} for r in parse_rows(dec_result)
            ]

    except Exception as exc:
        logger.warning("Failed to load product context for %s: %s", product_id, exc)

    return context


# ── E3a — CI/CD Generator ─────────────────────────────────────────────────────

_CI_PROMPT = """You are an expert DevOps engineer generating a {target} CI/CD workflow for a software project.

Project context (from ACE code graph):
Stack capabilities: {capabilities}
Quality gap profile (dimensions below 70%): {gap_profile}

Generate a production-ready {target} workflow file that:
1. Runs on push to main and pull_request events
2. Includes linting and type checking appropriate to the detected stack
3. Runs the test suite (use pytest for Python, jest/vitest for Node)
4. Sets coverage gates calibrated to current gap scores:
   - For each dimension below 50%: add a blocking gate
   - For each dimension 50-70%: add a warning gate
5. Includes security scanning (Semgrep if available)
6. Caches dependencies for performance
7. Uses environment variables for secrets (never hardcode)

Key decisions to honor: {decisions}

Return ONLY the raw YAML/config file content — no markdown fences, no explanation.
The file should be immediately usable. Infer the exact syntax for {target} format."""

_CI_PATHS = {
    "github_actions": ".github/workflows/ci.yml",
    "gitlab_ci": ".gitlab-ci.yml",
    "circleci": ".circleci/config.yml",
}


async def run_ci_generator(
    product_id: str,
    target: str = "github_actions",
    repo_path: str = ".",
) -> dict:
    """Generate a CI/CD workflow file parameterized from the ACE code graph.

    Args:
        product_id: Product context for graph queries.
        target: CI system target — 'github_actions', 'gitlab_ci', 'circleci'.
        repo_path: Local repo path for stack detection (optional).

    Returns:
        {target, content, suggested_path, stack, coverage_gates, error?}
    """
    if target not in CI_TARGETS:
        return {
            "target": target,
            "content": "",
            "error": f"Unknown target {target!r}. Valid: {sorted(CI_TARGETS)}",
        }

    ctx = await _load_product_context(product_id)

    # Format coverage gates description
    gates = []
    for gap in ctx["gap_profile"]:
        level = "blocking" if gap["avg_score"] < 0.5 else "warning"
        gates.append(f"  {gap['dimension']}: {gap['avg_score']:.0%} ({level})")

    # Detect stack hints from capabilities
    stack_hints = _infer_stack_from_capabilities(ctx["capabilities"])

    prompt = _CI_PROMPT.format(
        target=target,
        capabilities=", ".join(stack_hints) if stack_hints else "Python + FastAPI (inferred)",
        gap_profile="\n".join(gates) if gates else "  No gaps below 70% — all disciplines healthy",
        decisions="\n".join(f"  • {d['title']}: {d['rationale']}" for d in ctx["top_decisions"][:5])
        or "  No recent decisions captured",
    )

    try:
        llm = get_llm()
        content = await llm.complete(prompt, max_tokens=2048)
        return {
            "target": target,
            "content": content,
            "suggested_path": _CI_PATHS[target],
            "stack": stack_hints,
            "coverage_gates": [g["dimension"] for g in ctx["gap_profile"] if g["avg_score"] < 0.5],
        }
    except Exception as exc:
        logger.warning("CI generator failed for %s: %s", target, exc)
        return {"target": target, "content": "", "error": str(exc)}


# ── E3b — IaC Generator ───────────────────────────────────────────────────────

_DEPLOY_PROMPT = """You are an expert infrastructure engineer generating a {target} deployment configuration.

Project context (from ACE code graph):
Capabilities (services/stack detected): {capabilities}
Inferred services: {services}

Generate a production-ready {target} configuration that:
1. Defines all detected services with correct port mappings
2. Configures environment variable injection (no hardcoded secrets)
3. Sets appropriate resource limits for the detected stack
4. Includes health check endpoints where applicable
5. Configures persistent volumes for databases
6. Sets up networking between services

For Docker Compose: use version '3.8', define networks, use named volumes.
For Railway: generate railway.toml with correct service definitions.
For Coolify: generate docker-compose.coolify.yml with Coolify-compatible labels.
For Kamal: generate config/deploy.yml with correct roles and accessories.

Stack-specific notes:
- FastAPI: expose port 8000, use uvicorn workers
- SurrealDB: expose port 8000, mount /data volume
- Redis: expose port 6379, use appendonly yes
- Next.js: expose port 3000, standalone output mode
- PostgreSQL: expose port 5432, mount /var/lib/postgresql/data

Return ONLY the raw config file — no markdown fences, no explanation."""

_DEPLOY_PATHS = {
    "docker_compose": "docker-compose.yml",
    "railway": "railway.toml",
    "coolify": "docker-compose.coolify.yml",
    "kamal": "config/deploy.yml",
}


async def run_deploy_generator(
    product_id: str,
    target: str = "docker_compose",
    repo_path: str = ".",
) -> dict:
    """Generate a deployment manifest parameterized from the ACE code graph.

    Args:
        product_id: Product context for graph queries.
        target: Deploy target — 'docker_compose', 'railway', 'coolify', 'kamal'.
        repo_path: Local repo path for additional service detection.

    Returns:
        {target, content, suggested_path, services_detected, error?}
    """
    if target not in DEPLOY_TARGETS:
        return {
            "target": target,
            "content": "",
            "error": f"Unknown target {target!r}. Valid: {sorted(DEPLOY_TARGETS)}",
        }

    ctx = await _load_product_context(product_id)
    stack_hints = _infer_stack_from_capabilities(ctx["capabilities"])
    services = _infer_services_from_stack(stack_hints, ctx["capabilities"])

    prompt = _DEPLOY_PROMPT.format(
        target=target,
        capabilities=", ".join(stack_hints) if stack_hints else "Python + FastAPI (inferred)",
        services=", ".join(services) if services else "api (main service)",
    )

    try:
        llm = get_llm()
        content = await llm.complete(prompt, max_tokens=2048)
        return {
            "target": target,
            "content": content,
            "suggested_path": _DEPLOY_PATHS[target],
            "services_detected": services,
        }
    except Exception as exc:
        logger.warning("Deploy generator failed for %s: %s", target, exc)
        return {"target": target, "content": "", "error": str(exc)}


# ── E3c — Docs + Diagram Generator ───────────────────────────────────────────

_MERMAID_PROMPT = """Generate a Mermaid architecture diagram for this software project.

Capabilities and modules (from ACE code graph):
{capabilities}

Key architectural decisions:
{decisions}

Generate a Mermaid diagram using graph LR or graph TD (whichever fits best) that shows:
- Main modules/services as nodes
- Dependencies and data flows as edges
- Highlight the core value-delivering path with a distinctive style
- Group related modules in subgraphs

Return ONLY the raw Mermaid syntax — no markdown fences, no explanation, no comments."""

_ONBOARDING_PROMPT = """Generate an onboarding guide for a new developer joining this project.

Project context (from ACE intelligence graph):
Stack: {stack}
Key capabilities: {capabilities}
Architectural decisions made: {decisions}
Known gaps (areas to be careful): {gaps}

Structure the guide as:
1. What this project does (2-3 sentences from capabilities)
2. Tech stack (list with versions where known)
3. Key architectural patterns (from decisions)
4. First things to run (setup commands, typical for the stack)
5. Areas that need care (from gap profile — where quality is lower)
6. Key conventions ACE has captured (from decisions)

Return a concise markdown document. Be specific — use actual capability names and decision rationale."""

_API_PROMPT = """Generate API reference documentation for this project.

Capabilities (services, endpoints, integrations from ACE graph):
{capabilities}

Key decisions affecting the API:
{decisions}

Generate markdown documentation that:
1. Lists the main API surface (endpoints grouped by domain)
2. Notes authentication patterns used
3. Describes request/response patterns
4. Highlights any API design decisions captured

Return concise markdown — focus on what developers need to know, not boilerplate."""


async def run_docs_generator(
    product_id: str,
    format: str = "onboarding_guide",
    repo_path: str = ".",
) -> dict:
    """Generate documentation artifacts from the ACE intelligence graph.

    Args:
        product_id: Product context for graph queries.
        format: Output format — 'mermaid', 'onboarding_guide', 'api_reference'.
        repo_path: Local repo path (used for additional context).

    Returns:
        {format, content, title, error?}
    """
    if format not in DOCS_FORMATS:
        return {
            "format": format,
            "content": "",
            "error": f"Unknown format {format!r}. Valid: {sorted(DOCS_FORMATS)}",
        }

    ctx = await _load_product_context(product_id)
    stack_hints = _infer_stack_from_capabilities(ctx["capabilities"])

    cap_summary = "\n".join(
        f"  - {c.get('title', c.get('slug', '?'))} ({c.get('category', '?')})" for c in ctx["capabilities"][:20]
    )
    decision_summary = "\n".join(f"  - {d['title']}: {d['rationale']}" for d in ctx["top_decisions"][:8])
    gap_summary = "\n".join(
        f"  - {g['dimension']}: {g['avg_score']:.0%} ({g['gap_count']} gaps)" for g in ctx["gap_profile"]
    )

    if format == "mermaid":
        prompt = _MERMAID_PROMPT.format(
            capabilities=cap_summary or "  No capabilities mapped yet",
            decisions=decision_summary or "  No decisions captured",
        )
        title = "Architecture Diagram"
    elif format == "onboarding_guide":
        prompt = _ONBOARDING_PROMPT.format(
            stack=", ".join(stack_hints) if stack_hints else "detected from code graph",
            capabilities=cap_summary or "  No capabilities mapped yet",
            decisions=decision_summary or "  No decisions captured",
            gaps=gap_summary or "  All disciplines healthy",
        )
        title = "Developer Onboarding Guide"
    else:  # api_reference
        prompt = _API_PROMPT.format(
            capabilities=cap_summary or "  No capabilities mapped yet",
            decisions=decision_summary or "  No decisions captured",
        )
        title = "API Reference"

    try:
        llm = get_llm()
        content = await llm.complete(prompt, max_tokens=3000)
        return {
            "format": format,
            "content": content,
            "title": title,
        }
    except Exception as exc:
        logger.warning("Docs generator failed for %s: %s", format, exc)
        return {"format": format, "content": "", "title": "", "error": str(exc)}


# ── E3d — Changelog Generator ─────────────────────────────────────────────────

_CHANGELOG_PROMPT = """You are enriching a software changelog with architectural decision rationale.

Recent git commits:
{commits}

Decisions captured in this period (from ACE decision graph):
{decisions}

For each commit entry:
1. Keep the original commit message
2. If a captured decision explains WHY this change was made, add a brief note: "Why: [rationale]"
3. Group commits by type if possible: Features, Fixes, Refactoring, Dependencies, Docs
4. Only add rationale where there's a real match — don't invent explanations

Format as clean markdown changelog. Use this structure:
## [version or date] - [date]

### Features
- commit message [Why: decision rationale if applicable]

### Bug Fixes
- ...

Return only the changelog markdown — no explanation."""


async def run_changelog_generator(
    product_id: str,
    since_tag: str | None = None,
    max_entries: int = 50,
    repo_path: str = ".",
) -> dict:
    """Generate a decision-enriched changelog from git history.

    Reads git log and enriches commit entries with captured decision rationale
    from the ACE decision graph, linking each code change to its 'why'.

    Args:
        product_id: Product context for decision graph queries.
        since_tag:  Git tag to start from. None = last 30 days of commits.
        max_entries: Maximum commits to include.
        repo_path:  Path to git repo.

    Returns:
        {changelog, commit_count, decisions_linked, error?}
    """
    import os

    abs_path = os.path.abspath(repo_path)

    # Get git log
    commits = _fetch_git_commits(abs_path, since_tag, max_entries)
    if not commits:
        return {
            "changelog": "",
            "commit_count": 0,
            "decisions_linked": 0,
            "error": "No commits found" if not since_tag else f"No commits since {since_tag}",
        }

    # Load decisions from the same timeframe
    decisions = await _load_recent_decisions(product_id, days=90)

    commit_lines = "\n".join(f"  {c['hash']} {c['date']} {c['message']}" for c in commits[:max_entries])
    decision_lines = (
        "\n".join(
            f"  [{d.get('discipline', '?')}] {d.get('title', '')}: {d.get('rationale', '')[:150]}"
            for d in decisions[:20]
        )
        or "  No decisions captured in this period"
    )

    prompt = _CHANGELOG_PROMPT.format(
        commits=commit_lines,
        decisions=decision_lines,
    )

    try:
        llm = get_llm()
        content = await llm.complete(prompt, max_tokens=2048)
        return {
            "changelog": content,
            "commit_count": len(commits),
            "decisions_linked": len(decisions),
        }
    except Exception as exc:
        logger.warning("Changelog generator failed: %s", exc)
        return {"changelog": "", "commit_count": len(commits), "decisions_linked": 0, "error": str(exc)}


def _fetch_git_commits(repo_path: str, since_tag: str | None, max_entries: int) -> list[dict]:
    """Fetch recent git commits as structured dicts."""
    try:
        cmd = ["git", "-C", repo_path, "log", f"--max-count={max_entries}", "--format=%H|%as|%s"]
        if since_tag:
            cmd.append(f"{since_tag}..HEAD")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return []
        commits = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0][:7], "date": parts[1], "message": parts[2]})
        return commits
    except Exception:
        return []


async def _load_recent_decisions(product_id: str, days: int = 90) -> list[dict]:
    """Load recent decisions from the ACE graph."""
    try:
        async with pool.connection() as db:
            result = await db.query(
                """SELECT title, rationale, discipline, created_at
                   FROM decision
                   WHERE product = <record>$product
                     AND created_at > time::now() - <duration>$days_str
                   ORDER BY created_at DESC LIMIT 20""",
                {"product": product_id, "days_str": f"{days}d"},
            )
            return parse_rows(result)
    except Exception:
        return []


# ── Shared helpers ────────────────────────────────────────────────────────────


def _infer_stack_from_capabilities(capabilities: list[dict]) -> list[str]:
    """Infer stack technologies from capability slugs and titles."""
    stack = set()
    combined = " ".join(
        (c.get("slug", "") + " " + c.get("title", "") + " " + c.get("category", "")).lower() for c in capabilities
    )
    checks = [
        ("python", ["python", "fastapi", "django", "flask", "uvicorn", "pytest"]),
        ("fastapi", ["fastapi"]),
        ("node", ["node", "npm", "express", "next"]),
        ("typescript", ["typescript", "tsx", "ts"]),
        ("react", ["react", "tsx", "jsx", "nextjs", "next.js"]),
        ("nextjs", ["nextjs", "next.js"]),
        ("surrealdb", ["surrealdb", "surreal"]),
        ("postgres", ["postgres", "postgresql"]),
        ("redis", ["redis"]),
        ("docker", ["docker", "container"]),
        ("terraform", ["terraform", "iac", "infrastructure"]),
    ]
    for tech, keywords in checks:
        if any(kw in combined for kw in keywords):
            stack.add(tech)
    return sorted(stack) or ["python"]


def _infer_services_from_stack(stack: list[str], capabilities: list[dict]) -> list[str]:
    """Infer deployable services from stack + capabilities."""
    services = ["api"]  # Always assume an API service
    if "nextjs" in stack or "react" in stack:
        services.append("web")
    if "surrealdb" in stack:
        services.append("surrealdb")
    if "postgres" in stack:
        services.append("postgres")
    if "redis" in stack:
        services.append("redis")
    return services
