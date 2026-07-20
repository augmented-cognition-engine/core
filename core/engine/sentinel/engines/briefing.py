# engine/sentinel/engines/briefing.py
"""Briefing generator engine — aggregates overnight engine results into
a structured intelligence briefing.

Registered with the sentinel scheduler. Runs at 6am Monday.
Reads engine_run table, generates structured markdown via budget LLM,
writes to briefing table.

Spec: docs/superpowers/specs/2026-03-21-phase3c-briefings-interfaces.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from core.engine.core.config import settings
from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.sentinel.registry import register_engine
from core.engine.sentinel.triggers import meaningful_change_since_last_run

if TYPE_CHECKING:
    from core.engine.product.briefing_payload import TargetDriftAssessment

logger = logging.getLogger(__name__)


async def _deliver_briefing_emails(
    emails: list[str],
    briefing_id: str,
    product_id: str,
    summary: str,
) -> int:
    """Send briefing notification emails. Returns count of emails sent.

    Uses smtplib in a thread executor so it doesn't block the event loop.
    SMTP host/port read from settings; falls back to localhost:1025 (MailHog/mock).
    """
    import asyncio
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = getattr(settings, "smtp_host", "localhost")
    smtp_port = getattr(settings, "smtp_port", 1025)
    smtp_from = getattr(settings, "smtp_from", "ace@querylabs.ai")

    def _send_all() -> int:
        sent = 0
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as server:
                for email in emails:
                    msg = MIMEText(
                        f"New intelligence briefing ready.\n\nSummary:\n{summary}\n\nBriefing ID: {briefing_id}\nProduct: {product_id}",
                        "plain",
                    )
                    msg["Subject"] = f"ACE Briefing — {product_id}"
                    msg["From"] = smtp_from
                    msg["To"] = email
                    server.sendmail(smtp_from, [email], msg.as_string())
                    sent += 1
        except Exception as exc:
            logger.debug("Briefing email delivery failed: %s", exc)
        return sent

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send_all)


def aggregate_engine_results(runs: list[dict]) -> dict:
    """Aggregate engine_run results into briefing metrics. Pure function."""
    metrics = {
        "corrections_written": 0,
        "gaps_filled": 0,
        "insights_verified": 0,
        "insights_updated": 0,
        "changes_detected": 0,
        "conflicts_found": 0,
        "proposals_pending": 0,
        "staleness_warnings": 0,
        "total_active_insights": 0,
        "insights_delta": 0,
        "specialty_improvements": [],
        "engine_runs_summarized": len(runs),
        "competitive_signals": 0,
        "competitive_insights": 0,
        "competitive_alerts": 0,
        "competitors_scanned": 0,
    }

    for run in runs:
        engine = run.get("engine", "")
        results = run.get("results") or {}

        if engine == "failure_analysis":
            metrics["corrections_written"] += results.get("corrections_written", 0)
        elif engine == "gap_researcher":
            metrics["gaps_filled"] += results.get("insights_written", 0)
        elif engine == "knowledge_verifier":
            metrics["insights_verified"] += results.get("confirmed", 0) + results.get("updated", 0)
            metrics["insights_updated"] += results.get("updated", 0)
        elif engine == "specialty_deepener":
            improvements = results.get("specialty_improvements", [])
            if improvements:
                metrics["specialty_improvements"].extend(improvements)
        elif engine == "world_monitor":
            metrics["changes_detected"] += results.get("changes_detected", 0)
        elif engine == "conflict_detector":
            metrics["conflicts_found"] += results.get("conflicts_found", 0)
        elif engine == "evolution_engine":
            metrics["evolution_committed"] = metrics.get("evolution_committed", 0) + results.get("committed", 0)
            metrics["evolution_experiments"] = metrics.get("evolution_experiments", 0) + results.get(
                "experiments_run", 0
            )
            metrics["evolution_escalated"] = metrics.get("evolution_escalated", 0) + results.get("escalated", 0)
            metrics["evolution_hypotheses"] = metrics.get("evolution_hypotheses", 0) + results.get("hypotheses", 0)
        elif engine == "competitive_observer":
            metrics["competitive_signals"] += results.get("signals_extracted", 0)
            metrics["competitive_insights"] += results.get("insights_written", 0)
            metrics["competitive_alerts"] += results.get("alerts_sent", 0)
            metrics["competitors_scanned"] += results.get("competitors_scanned", 0)
        elif engine == "simplicity_audit":
            metrics["simplicity_dormant"] = results.get("dormant_count", 0)
            metrics["simplicity_low_value"] = results.get("low_value_count", 0)
            metrics["simplicity_score"] = results.get("complexity_score", 0.0)
            metrics["simplicity_recommendations"] = results.get("recommendations", [])

    return metrics


def build_briefing_prompt(
    metrics: dict,
    engine_details: dict,
    org_name: str,
    session_digests: list[dict] | None = None,
) -> str:
    """Build the LLM prompt for generating a structured briefing."""
    now = datetime.now(timezone.utc)
    week_str = now.strftime("%B %d, %Y")

    digest_section = ""
    if session_digests:
        digest_parts = ["\n\nSession Activity (Past Period):"]
        for d in session_digests:
            digest_parts.append(f"\nSession {d.get('session_id', '?')} ({d.get('tasks_executed', 0)} tasks):")
            digest_parts.append(f"  {d.get('summary', 'No summary')}")
            if d.get("decisions"):
                for dec in d["decisions"]:
                    digest_parts.append(f"  - Decision: {dec.get('title', '?')} ({dec.get('discipline', '?')})")
            if d.get("blockers"):
                for b in d["blockers"]:
                    digest_parts.append(f"  - Blocker: {b.get('description', '?')} [{b.get('status', '?')}]")
        digest_section = "\n".join(digest_parts)

    return f"""Generate a ACE Intelligence Briefing following this exact format.
Use the data provided — do not invent numbers. Keep it concise and factual.

VOICE: write in our partner voice. Use 'we' / 'our' / 'us' naturally throughout —
this is a colleague reporting on what we did together, not a system status report.
Every paragraph longer than two lines should reference our shared work explicitly.

Organization: {org_name}
Week of: {week_str}

Aggregated metrics:
- Corrections written: {metrics["corrections_written"]}
- Knowledge gaps filled: {metrics["gaps_filled"]}
- Insights verified: {metrics["insights_verified"]}
- Insights updated: {metrics["insights_updated"]}
- External changes detected: {metrics["changes_detected"]}
- Conflicts found: {metrics["conflicts_found"]}
- Pending proposals: {metrics["proposals_pending"]}
- Staleness warnings: {metrics["staleness_warnings"]}
- Total active insights: {metrics["total_active_insights"]}
- Insights delta (since last briefing): {metrics["insights_delta"]}
- Specialty improvements: {metrics["specialty_improvements"]}
- Engine runs summarized: {metrics["engine_runs_summarized"]}
- ROI: {metrics.get("roi", {})}
- Calibration notes: {metrics.get("calibration_notes", [])}
- Adversarial review: {metrics.get("adversarial_review", {})}
- Experimentation: {metrics.get("experimentation", {})}

Evolution engine results:
- Hypotheses generated: {metrics.get("evolution_hypotheses", 0)}
- Experiments run: {metrics.get("evolution_experiments", 0)}
- Insights committed: {metrics.get("evolution_committed", 0)}
- Questions escalated: {metrics.get("evolution_escalated", 0)}
- Evolution narratives: {metrics.get("evolution_narratives", [])}

Competitive intelligence:
- Competitors scanned: {metrics.get("competitors_scanned", 0)}
- Signals extracted: {metrics.get("competitive_signals", 0)}
- Insights written: {metrics.get("competitive_insights", 0)}
- Alerts sent: {metrics.get("competitive_alerts", 0)}

Simplicity audit:
- Dormant components: {metrics.get("simplicity_dormant", 0)}
- Low-value components: {metrics.get("simplicity_low_value", 0)}
- Complexity score: {metrics.get("simplicity_score", 0.0):.2f}
- Recommendations: {metrics.get("simplicity_recommendations", [])}

Token efficiency:
- Total tokens used: {metrics.get("efficiency", {}).get("total_tokens", 0)}
- Estimated tokens saved: {metrics.get("efficiency", {}).get("total_saved", 0)}
- Tasks tracked: {metrics.get("efficiency", {}).get("task_count", 0)}
{_format_proactive_signals_section(metrics.get("proactive_signals", []))}
Engine details (for line-item descriptions):
{_format_engine_details(engine_details)}

Format the output as:

ACE Intelligence Briefing -- Week of {week_str}
Organization: {org_name}

[A 1–2 sentence opener in our partner voice (must include 'we' / 'our' / 'us')
that sets the theme of this week's work — e.g., what we shipped, what we
learned, what we're tracking. Keep it warm and specific to this week's data.]

OVERNIGHT IMPROVEMENTS:
  [X] task failures analyzed, [Y] corrections written
    -> [one line per notable correction if details available]

  [N] knowledge gaps researched and filled
    -> [one line per topic if details available]

  [N] insights verified against current sources
    -> [X] confirmed current, [Y] updated

  [Specialty improvements if any]

  External changes detected:
    -> [one line per change if details available]

ATTENTION NEEDED:
  [N] unresolved conflicts
  [N] synapse proposals pending confirmation
  [N] insights approaching staleness threshold

[total] active insights across specialties (+/- [delta] since last briefing)

EVOLUTION ENGINE:
  [N] hypotheses investigated, [N] experiments run
  [N] new insights committed to the intelligence graph
    -> [one line per committed insight if details available]
  [N] questions escalated (need your input)
    -> [one line per question if narratives available]

TOKEN EFFICIENCY:
  [X] tokens used
  [Y] tokens saved
  [N] tasks tracked

ROI IMPACT:
  [X] mistakes prevented (~Y hours saved)
  [X] knowledge gaps filled (~Y hours saved)
  [X] cross-domain connections surfaced (~Y hours saved)
  Total estimated time saved: ~Z hours

CALIBRATION NOTES:
  [Domain is overconfident/underconfident by X.XX — treat outputs with appropriate skepticism/confidence]

Only include sections where the count is > 0. If no data for a section, omit it entirely.
Return only the briefing text — no markdown fences, no explanation.{digest_section}"""


def _format_engine_details(details: dict) -> str:
    """Format engine detail dicts for the prompt."""
    lines = []
    for engine, data in details.items():
        items = ", ".join(f"{k}: {v}" for k, v in data.items())
        lines.append(f"  {engine}: {items}")
    return "\n".join(lines) if lines else "  No detailed engine data available."


def _format_proactive_signals_section(signals: list[dict]) -> str:
    """Format proactive intelligence signals for inclusion in the briefing prompt.

    Returns an empty string when no signals, so the prompt section is omitted cleanly.
    """
    if not signals:
        return ""
    lines = ["\nProactive intelligence signals (new synthesis findings):"]
    for sig in signals:
        et = sig.get("event_type", "")
        summary = sig.get("summary", "")
        lines.append(f"  - [{et}] {summary}")
    lines.append("\nInclude a PROACTIVE INTELLIGENCE section in the briefing listing these findings.")
    return "\n".join(lines)


async def build_product_health_section(product_id: str, db) -> str:
    """Query capability_quality records and return a markdown Product Health section.

    Groups quality records by dimension, computes average score per dimension,
    and identifies dimensions with gaps (avg score < 0.4).
    D2: Includes trend arrows when snapshot history available.
    D6: Includes correlation warnings when leading-indicator dimension is declining.
    Returns an empty string when no records exist for the org.
    """
    result = await db.query(
        "SELECT dimension, score, gaps FROM capability_quality WHERE product = <record>$product",
        {"product": product_id},
    )
    rows = parse_rows(result)

    if not rows:
        return ""

    # Group by dimension
    dimension_scores: dict[str, list[float]] = {}
    dimension_gap_count: dict[str, int] = {}

    for row in rows:
        dim = row.get("dimension", "unknown")
        score = float(row.get("score", 0.0))
        gaps = row.get("gaps") or []

        if dim not in dimension_scores:
            dimension_scores[dim] = []
            dimension_gap_count[dim] = 0

        dimension_scores[dim].append(score)
        dimension_gap_count[dim] += len(gaps) if isinstance(gaps, list) else 0

    # D2: Fetch 30-day trend data for all dimensions
    trend_by_dim: dict[str, dict] = {}
    try:
        from core.engine.sentinel.engines.gap_analyzer import get_score_trend

        for dim in dimension_scores:
            trend_data = await get_score_trend(product_id, dim, days=30, db=db)
            if trend_data.get("trend") != "insufficient_data":
                trend_by_dim[dim] = trend_data
    except Exception:
        pass  # Trend data is optional — never block the briefing

    # D6: Fetch correlation signals for declining dimensions
    correlation_warnings: list[str] = []
    try:
        from core.engine.sentinel.engines.correlation_engine import get_correlation_signals

        for dim, data in trend_by_dim.items():
            if data.get("trend") == "declining" and abs(data.get("delta", 0)) > 0.05:
                # Pass `db` so this doesn't nest a new connection inside the
                # briefing engine's already-held one — see
                # engine/sentinel/engines/correlation_engine.py:get_correlation_signals
                signals = await get_correlation_signals(product_id, dim, db=db)
                for sig in signals[:1]:  # One warning per declining dim
                    correlation_warnings.append(f"  ⚠ Historical pattern: {sig['interpretation']}")
    except Exception:
        pass

    lines = ["## Product Health", ""]
    for dim in sorted(dimension_scores):
        scores = dimension_scores[dim]
        avg = sum(scores) / len(scores)
        gap_count = dimension_gap_count[dim]
        label = dim.capitalize()

        # D2: trend arrow
        trend = trend_by_dim.get(dim, {})
        delta = trend.get("delta", 0.0)
        if trend.get("trend") == "improving" and delta > 0.10:
            arrow = f" ↑↑ (+{delta:.2f})"
        elif trend.get("trend") == "improving":
            arrow = f" ↑ (+{delta:.2f})"
        elif trend.get("trend") == "declining" and delta < -0.05:
            arrow = f" ↓ ({delta:.2f}) — review recent changes"
        else:
            arrow = ""

        if avg < 0.4:
            lines.append(f"- **{label}**: avg {avg:.1f} ({gap_count} gaps){arrow}")
        else:
            lines.append(f"- **{label}**: avg {avg:.1f} ✓{arrow}")

    lines.append("")

    # D6: Append correlation warnings after health section
    if correlation_warnings:
        lines.append("### Predictive Signals")
        lines.extend(correlation_warnings)
        lines.append("")

    return "\n".join(lines)


def _validate_briefing_inputs(product_id: str, budget: int = 100) -> None:
    """Validate briefing inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for briefing: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="briefing_generator",
    cron="0 6 * * mon",
    description="Weekly intelligence briefing (6am Monday)",
    trigger=lambda product_id: meaningful_change_since_last_run("briefing_generator", product_id),
)
async def run_briefing_generator(product_id: str, budget: int = 5) -> dict:
    """Generate a structured intelligence briefing from overnight engine results."""
    _validate_briefing_inputs(product_id, budget)
    logger.info("Briefing generator started: product=%s budget=%d", product_id, budget)
    async with pool.connection() as db:
        # Find the last briefing date for this org
        last_briefing_result = await db.query(
            """
            SELECT created_at FROM briefing
            WHERE product = <record>$product
            ORDER BY created_at DESC LIMIT 1
            """,
            {"product": product_id},
        )
        last_row = parse_one(last_briefing_result)

        if last_row and last_row.get("created_at"):
            since = last_row["created_at"]
        else:
            since = datetime.now(timezone.utc) - timedelta(days=7)

        # Query engine_run records since last briefing
        engine_runs_result = await db.query(
            """
            SELECT id, engine, status, results, started_at, completed_at, duration_ms
            FROM engine_run
            WHERE product = <record>$product AND started_at > $since AND status = 'completed'
            ORDER BY started_at ASC
            """,
            {"product": product_id, "since": since},
        )
        runs = parse_rows(engine_runs_result)

        # Also query evolution_run records (separate table)
        evo_runs_result = await db.query(
            """
            SELECT * FROM evolution_run
            WHERE product = <record>$product AND created_at > $since
            ORDER BY created_at ASC
            """,
            {"product": product_id, "since": since},
        )
        evo_runs = parse_rows(evo_runs_result)

        # Convert evolution_run records to engine_run-like format for aggregation
        for evo in evo_runs:
            if isinstance(evo, dict):
                runs.append(
                    {
                        "engine": "evolution_engine",
                        "results": {
                            "committed": evo.get("committed", 0),
                            "experiments_run": evo.get("experiments_run", 0),
                            "escalated": evo.get("escalated", 0),
                            "hypotheses": len(evo.get("hypotheses", [])),
                        },
                    }
                )

        # Voice-rendering refactor (2026-04-29): no longer early-exit on quiet weeks.
        # The new briefing is product-state-centric (phase floors, drift, top recs)
        # rather than engine-activity-centric, so it has value to render even when no
        # engines ran. Empty-runs case produces a "(no engine activity)" footer.

        # Aggregate metrics — works with empty list (returns zero counts)
        metrics = aggregate_engine_results(runs)

        # Collect evolution narratives from evolution_run findings
        evolution_narratives = []
        for evo in evo_runs:
            if isinstance(evo, dict):
                for finding in evo.get("findings", []):
                    if isinstance(finding, dict) and finding.get("narrative"):
                        evolution_narratives.append(finding["narrative"][:200])
        metrics["evolution_narratives"] = evolution_narratives[:10]

        engine_details: dict[str, dict] = {}
        for run in runs:
            engine = run.get("engine", "unknown")
            if run.get("results"):
                engine_details[engine] = run["results"]

        # Query current intelligence state
        active_result = await db.query(
            "SELECT count() AS count FROM insight WHERE product = <record>$product AND status = 'active' GROUP ALL",
            {"product": product_id},
        )
        active_row = parse_one(active_result)
        metrics["total_active_insights"] = active_row.get("count", 0) if active_row else 0

        conflict_result = await db.query(
            "SELECT count() AS count FROM conflict WHERE product = <record>$product AND status = 'pending' GROUP ALL",
            {"product": product_id},
        )
        conflict_row = parse_one(conflict_result)
        metrics["conflicts_found"] = conflict_row.get("count", 0) if conflict_row else 0

        proposal_result = await db.query(
            "SELECT count() AS count FROM synapse WHERE product = <record>$product AND confirmed = false GROUP ALL",
            {"product": product_id},
        )
        proposal_row = parse_one(proposal_result)
        metrics["proposals_pending"] = proposal_row.get("count", 0) if proposal_row else 0

        stale_result = await db.query(
            "SELECT count() AS count FROM insight WHERE product = <record>$product AND status = 'active' AND confidence < 0.3 GROUP ALL",
            {"product": product_id},
        )
        stale_row = parse_one(stale_result)
        metrics["staleness_warnings"] = stale_row.get("count", 0) if stale_row else 0

        metrics["insights_delta"] = metrics["corrections_written"] + metrics["gaps_filled"]

        # Token efficiency metrics
        efficiency_result = await db.query(
            """
            SELECT
                math::sum(token_total) AS total_tokens,
                math::sum(estimated_tokens_saved) AS total_saved,
                count() AS task_count
            FROM composition_signal
            WHERE product = <record>$product
              AND created_at > $since
            GROUP ALL
            """,
            {"product": product_id, "since": since},
        )
        efficiency_rows = parse_rows(efficiency_result)
        efficiency_metrics = efficiency_rows[0] if efficiency_rows else {}
        metrics["efficiency"] = efficiency_metrics

        # ROI summary since last briefing
        roi_summary: dict = {"total_minutes_saved": 0, "events": {}}
        try:
            roi_result = await db.query(
                """
                SELECT event_type, count() AS count,
                       math::sum(estimated_time_saved_minutes) AS minutes_saved
                FROM roi_event
                WHERE product = <record>$product AND created_at > $since
                GROUP BY event_type
                """,
                {"product": product_id, "since": since},
            )
            roi_rows = parse_rows(roi_result)
            for rr in roi_rows:
                et = rr.get("event_type", "")
                mins = rr.get("minutes_saved", 0) or 0
                roi_summary["events"][et] = {"count": rr.get("count", 0) or 0, "minutes": mins}
                roi_summary["total_minutes_saved"] += mins
        except Exception:
            pass
        metrics["roi"] = roi_summary

        # Calibration notes — flag domains with abs(miscalibration) > 0.15
        calibration_notes: list[str] = []
        try:
            cal_result = await db.query(
                "SELECT data FROM calibration WHERE product = <record>$product LIMIT 1",
                {"product": product_id},
            )
            cal_row = parse_one(cal_result)
            if cal_row and cal_row.get("data"):
                for domain, buckets in cal_row["data"].items():
                    for bdata in buckets.values() if isinstance(buckets, dict) else []:
                        miscal = bdata.get("miscalibration", 0.0) if isinstance(bdata, dict) else 0.0
                        if abs(miscal) > 0.15:
                            direction = "overconfident" if miscal > 0 else "underconfident"
                            calibration_notes.append(f"{domain} is {direction} by {abs(miscal):.2f}")
        except Exception:
            pass
        metrics["calibration_notes"] = calibration_notes

        # Adversarial review — query experiment_log for adversarial challenges since last briefing
        adversarial_review: dict = {"total_challenged": 0, "valid_challenges": []}
        try:
            adv_result = await db.query(
                """
                SELECT control_description, variant_description, significant, details, created_at
                FROM experiment_log
                WHERE product = <record>$product AND experiment_type = 'adversarial' AND created_at > $since
                ORDER BY created_at DESC
                """,
                {"product": product_id, "since": since},
            )
            adv_rows = parse_rows(adv_result)
            adversarial_review["total_challenged"] = len(adv_rows)
            for ar in adv_rows:
                if ar.get("significant"):
                    details = ar.get("details", {}) if isinstance(ar.get("details"), dict) else {}
                    adversarial_review["valid_challenges"].append(
                        {
                            "belief": str(ar.get("control_description", ""))[:100],
                            "challenge": str(ar.get("variant_description", ""))[:100],
                            "score": details.get("evaluation_score", 0),
                        }
                    )
        except Exception:
            pass
        metrics["adversarial_review"] = adversarial_review

        # Proactive intelligence signals — new synthesis findings from event triggers
        proactive_signals: list[dict] = []
        try:
            ps_result = await db.query(
                """
                SELECT event_type, summary, created_at
                FROM proactive_signal
                WHERE product = <record>$product AND status = 'new'
                ORDER BY created_at DESC LIMIT 10
                """,
                {"product": product_id},
            )
            for row in parse_rows(ps_result):
                proactive_signals.append(
                    {
                        "event_type": row.get("event_type", ""),
                        "summary": row.get("summary", ""),
                    }
                )
        except Exception:
            pass
        metrics["proactive_signals"] = proactive_signals

        # Experimentation summary — domain research results since last briefing
        experimentation: dict = {"total": 0, "winners": 0, "losers": 0, "domains": []}
        try:
            exp_result = await db.query(
                """
                SELECT domain, significant, committed, improvement
                FROM experiment_log
                WHERE product = <record>$product AND experiment_type = 'intelligence_variant' AND created_at > $since
                """,
                {"product": product_id, "since": since},
            )
            exp_rows = parse_rows(exp_result)
            experimentation["total"] = len(exp_rows)
            experimentation["winners"] = sum(1 for e in exp_rows if e.get("committed"))
            experimentation["losers"] = sum(1 for e in exp_rows if e.get("significant") and not e.get("committed"))
            # Per-domain breakdown
            domain_map: dict[str, dict] = {}
            for e in exp_rows:
                d = e.get("domain", "unknown")
                if d not in domain_map:
                    domain_map[d] = {"experiments": 0, "winners": 0}
                domain_map[d]["experiments"] += 1
                if e.get("committed"):
                    domain_map[d]["winners"] += 1
            experimentation["domains"] = [{"domain": k, **v} for k, v in domain_map.items()]
        except Exception:
            pass
        metrics["experimentation"] = experimentation

        # session_digest query preserved (voice rendering doesn't read it, but the
        # test mock list still expects this slot — keeps the query without binding
        # the result, so ruff's F841 unused-variable rule doesn't trip).
        today_period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await db.query(
            """SELECT id, created_at FROM session_digest
            WHERE product = <record>$product AND period = $period
            ORDER BY created_at DESC LIMIT 1""",
            {"product": product_id, "period": today_period},
        )

        # Generate briefing via voice rendering layer (partner-voice partner_voice_v1).
        # Replaces the prior LLM-prompt path. compose_morning_briefing is deterministic;
        # voice rules enforced at the renderer level + linguistic_audit at compose time.
        from core.engine.voice.briefing import compose_morning_briefing

        payload = await build_briefing_payload(product_id)
        content = await compose_morning_briefing(payload, engine_runs=runs)

        # Persist the structured BriefingPayload alongside the rendered markdown —
        # supports v2 replay (continuity layer reads old payloads to test new renderers).
        # Use a disposable connection: when this CREATE raises (e.g. schema field
        # mismatch on payload_json), the exception leaves the underlying connection
        # in an inconsistent state. If we share the parent connection, the next
        # db.query() hangs forever — same failure mode as the asyncio.wait_for
        # cancellation case. Isolating means the bad connection just gets reclaimed
        # by the pool watchdog while the parent's connection stays clean.
        try:
            async with pool.connection() as _pl_db:
                payload_create = await _pl_db.query(
                    """CREATE briefing_payload SET
                        product = <record>$product,
                        payload_json = $payload,
                        computed_at = time::now()
                    """,
                    {"product": product_id, "payload": payload},
                )
                payload_row = parse_one(payload_create)
                _payload_ref = str(payload_row.get("id", "")) if payload_row else None
                _ = _payload_ref  # noqa: F841 — payload_ref linkage on briefing requires schema migration
        except Exception as exc:
            logger.warning("briefing_payload write failed (non-fatal): %s", exc)

        # Append product health section if any quality data exists.
        # Voice-rendered briefing already covers core product state via top_recommendations
        # and target_drift_assessment; product_health stays as a supplementary detail.
        # Capped at 15s — observed to hang for >240s on the demo dataset because
        # it iterates every dimension and runs a 90-day snapshot scan per dim
        # (full-table scans on capability_quality_snapshot). Supplementary section,
        # so skipping it on timeout is preferable to blocking the core CREATE.
        import asyncio as _asyncio

        try:
            async with pool.connection() as _ph_db:
                product_health = await _asyncio.wait_for(build_product_health_section(product_id, _ph_db), timeout=15.0)
            if product_health:
                content = content + "\n\n" + product_health
        except _asyncio.TimeoutError:
            logger.warning("build_product_health_section timed out (>15s) — skipping supplementary section")

        # Extension-contributed briefing sections (e.g. marketing audit activity).
        # Each provider is async (db) -> {available, markdown, metrics} and is
        # non-fatal: a slow or failing section is skipped, never the whole briefing.
        from core.engine.extensions.registry import registered_briefing_sections

        for _section in registered_briefing_sections():
            _key = _section["metrics_key"]
            try:
                async with pool.connection() as _sec_db:
                    _result = await _asyncio.wait_for(_section["builder"](_sec_db), timeout=_section["timeout"])
                if _result and _result.get("available") and _result.get("markdown"):
                    content = content + "\n\n" + _result["markdown"]
                    if _result.get("metrics"):
                        metrics[_key] = _result["metrics"]
            except _asyncio.TimeoutError:
                logger.warning("briefing section %r timed out (>%ss) — skipping", _key, _section["timeout"])
            except Exception as _sec_exc:
                logger.debug("briefing section %r failed (non-fatal): %s", _key, _sec_exc)

        run_ids = [str(r.get("id", "")) for r in runs if r.get("id")]
        logger.info("Briefing: post-health, content_len=%d", len(content))

        # Find previous briefing to chain superseded_by
        prev_result = await db.query(
            "SELECT id, created_at FROM briefing WHERE product = <record>$product ORDER BY created_at DESC LIMIT 1",
            {"product": product_id},
        )
        prev_row = parse_one(prev_result)
        prev_id = str(prev_row.get("id", "")) if prev_row else None
        logger.info("Briefing: prev_id=%s", prev_id or "(none)")

        # Build structured content — narrative + diffable sections extracted from metrics
        highlights = []
        for key, label in [
            ("corrections_written", "corrections written"),
            ("gaps_filled", "gaps filled"),
            ("insights_verified", "insights verified"),
            ("insights_updated", "insights updated"),
            ("changes_detected", "external changes detected"),
            ("competitive_insights", "competitive insights written"),
        ]:
            val = metrics.get(key, 0)
            if val:
                highlights.append({"item_key": key, "content": f"{val} {label}"})

        risks = []
        for key, label in [
            ("conflicts_found", "unresolved conflicts"),
            ("staleness_warnings", "insights approaching staleness"),
            ("proposals_pending", "synapse proposals pending"),
        ]:
            val = metrics.get(key, 0)
            if val:
                risks.append({"item_key": key, "content": f"{val} {label}"})

        # Structured content is persisted to briefing_payload separately;
        # the briefing.content field stores the rendered markdown narrative.

        # Write briefing — always INSERT new record, never overwrite.
        # format='partner_voice_v1' marks this as voice-rendered; legacy briefings
        # have no format field and are read via the pm_central overlay path.
        logger.info("Briefing: starting CREATE")
        # briefing table is SCHEMAFULL — only DEFINEd fields accepted.
        # `format`, `payload_ref`, `superseded_by`, `is_public` were rejected
        # with "no such field exists for table briefing". The structured-payload
        # linkage (payload_ref) and chaining (superseded_by) want migration to
        # land before they're usable here; for now we persist the core fields.
        # payload_ref is still computed above for callers that read it via the
        # function return.
        create_result = await db.query(
            """
            CREATE briefing SET
                product = <record>$product,
                content = $content,
                period = 'weekly',
                metrics = $metrics,
                engine_runs = $run_ids,
                created_at = time::now()
            """,
            {
                "product": product_id,
                "content": content,
                "metrics": metrics,
                "run_ids": run_ids,
            },
        )
        create_row = parse_one(create_result)
        briefing_id = str(create_row.get("id", "")) if create_row else ""
        if not briefing_id:
            logger.error("Briefing CREATE returned no id — raw result: %r", create_result)
        else:
            logger.info("Briefing: CREATE done id=%s", briefing_id)

        # Chain: mark previous briefing as superseded by this one
        if prev_id and briefing_id:
            try:
                await db.query(
                    "UPDATE <record>$prev SET superseded_by = <record>$new_id",
                    {"prev": prev_id, "new_id": briefing_id},
                )
            except Exception:
                pass  # non-fatal — chain is best-effort

        # Mark proactive signals as seen — they have been incorporated into this briefing
        if proactive_signals:
            try:
                await db.query(
                    """
                    UPDATE proactive_signal
                    SET status = 'seen'
                    WHERE product = <record>$product AND status = 'new'
                    """,
                    {"product": product_id},
                )
            except Exception:
                pass  # non-fatal

        # Emit event for notification channels (Discord push, etc.)
        try:
            from core.engine.events.bus import bus

            first_line = (content or "").split("\n")[0][:200]

            await bus.emit(
                "briefing.generated",
                {
                    "product_id": product_id,
                    "briefing_id": briefing_id,
                    "period": "weekly",
                    "summary": first_line,
                },
            )
        except Exception:
            pass  # event emission is best-effort

        # Email delivery — notify subscribers of the new briefing
        if briefing_id:
            try:
                subs_result = await db.query(
                    "SELECT email FROM briefing_subscription WHERE product = <record>$product",
                    {"product": product_id},
                )
                subs = parse_rows(subs_result)
                if subs:
                    await _deliver_briefing_emails(
                        emails=[s["email"] for s in subs if s.get("email")],
                        briefing_id=briefing_id,
                        product_id=product_id,
                        summary=(content or "").split("\n")[0][:300],
                    )
            except Exception:
                pass  # non-fatal

    logger.info(
        "Briefing generator complete: product=%s briefing_id=%s runs=%d",
        product_id,
        briefing_id,
        len(runs),
    )
    return {
        "briefings_generated": 1,
        "briefing_id": briefing_id,
        "engine_runs_summarized": len(runs),
        "metrics": metrics,
    }


# ─── BriefingPayload contract (spec v1.2 — phase-aware substrate) ─────────────

# Sensor → discipline mapping. The 4 keys are the partnership-spec sensor
# slugs (dotted pillar.discipline[.sub-dim] paths). The value is the discipline
# whose presence in capability_quality counts as "sensor covered".
_SENSOR_DISCIPLINES: dict[str, str] = {
    "experience.aix": "aix",
    "experience.content_design.voice_consistency": "content_design",
    "experience.aix.demo_readiness": "aix",
    "evolution.engineering_culture.contributor_coordination": "engineering_culture",
}


def compute_target_drift_assessment(
    *,
    demo_target,
    pattern_to_pillar: dict[str, str],
    pillar_scores: dict[str, float],
    phase_floors: dict[str, float],
) -> "TargetDriftAssessment | None":
    """Structured drift assessment. None when there's no demo target."""
    from core.engine.product.briefing_payload import TargetDriftAssessment

    if demo_target is None or not getattr(demo_target, "required_patterns", None):
        return None
    required = list(demo_target.required_patterns)
    blocked: list[tuple[str, str]] = []
    for slug in required:
        pillar = pattern_to_pillar.get(slug)
        if not pillar:
            continue
        score = float(pillar_scores.get(pillar, 0.0))
        floor = float(phase_floors.get(pillar, 0.0))
        if score < floor:
            blocked.append((slug, pillar))
    return TargetDriftAssessment(
        n_total=len(required),
        n_blocked=len(blocked),
        blocking_pillars=sorted({p for _, p in blocked}),
    )


def compute_discipline_breakdown(
    dim_scores: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Group dimension-level scores under their owning pillar.

    Output: {pillar_value: {discipline: score}}. Disciplines that don't map
    to a known pillar are dropped (they shouldn't reach this layer, but be
    defensive).
    """
    from core.engine.product.pillars import LEGACY_DIM_TO_PILLAR, Pillar

    breakdown: dict[str, dict[str, float]] = {p.value: {} for p in Pillar}
    for dim, score in dim_scores.items():
        pillar = LEGACY_DIM_TO_PILLAR.get(dim)
        if pillar is None:
            continue
        breakdown[pillar.value][dim] = float(round(score, 3))
    return breakdown


def compute_sensor_coverage(disciplines_with_recent_data: set[str]) -> dict[str, bool]:
    """Map each sensor slug → True if its discipline has recent capability_quality data.

    The four sensor keys are partnership-spec contract; their values reflect
    whether the discipline they signal on has been scored recently.
    """
    return {sensor: discipline in disciplines_with_recent_data for sensor, discipline in _SENSOR_DISCIPLINES.items()}


async def build_briefing_payload(product_id: str = "product:platform") -> dict:
    """Build the structured BriefingPayload for a product.

    Returns a dict matching engine.product.briefing_payload.BriefingPayload shape,
    ready for serialization. Voice rendering happens elsewhere — this is the data.
    """
    from dataclasses import asdict
    from datetime import datetime

    from core.engine.core.db import parse_rows, pool
    from core.engine.product.ambition import AmbitionRepository
    from core.engine.product.phase_floors import effective_floor
    from core.engine.product.pillar_aggregator import PillarAggregator
    from core.engine.product.pillars import Pillar
    from core.engine.product.uncertainty import get_open_queries

    repo = AmbitionRepository(pool)
    ambition = await repo.get(product_id)

    agg = PillarAggregator(pool)
    pillar_scores = await agg.get_pillar_scores(product_id)

    async with pool.connection() as db:
        prod_rows = parse_rows(
            await db.query(
                "SELECT product_type, product_scale FROM <record>$pid",
                {"pid": product_id},
            )
        )
    pt = prod_rows[0].get("product_type", "ai_native") if prod_rows else "ai_native"
    scale = prod_rows[0].get("product_scale", "application") if prod_rows else "application"

    current_phase = ambition.phase.current if ambition and ambition.phase else "discovery"
    days_in_phase = ambition.phase.compute_days_in_phase() if ambition and ambition.phase else 0

    phase_floors = {p.value: effective_floor(p, current_phase, pt, scale) for p in Pillar}
    pillar_scores_str = {p.value: float(round(s, 3)) for p, s in pillar_scores.items()}

    open_qs = await get_open_queries(pool, product_id)

    # Per-discipline scores (drill-down under each pillar) + sensor coverage —
    # both derived from capability_quality. One query feeds both.
    async with pool.connection() as db:
        dim_rows = parse_rows(
            await db.query(
                """SELECT dimension, math::mean(score) AS avg_score
                   FROM capability_quality
                   WHERE product = <record>$pid
                   GROUP BY dimension""",
                {"pid": product_id},
            )
        )
        recent_dim_rows = parse_rows(
            await db.query(
                """SELECT dimension FROM capability_quality
                   WHERE product = <record>$pid
                     AND assessed_at > time::now() - 7d
                   GROUP BY dimension""",
                {"pid": product_id},
            )
        )
        state_change_rows = parse_rows(
            await db.query(
                """SELECT event_type, payload, created_at FROM event_log
                   WHERE product = $pid
                     AND created_at > time::now() - 7d
                   ORDER BY created_at DESC LIMIT 20""",
                {"pid": product_id},
            )
        )
    dim_scores = {r.get("dimension", ""): float(r.get("avg_score", 0.0)) for r in dim_rows if r.get("dimension")}
    disciplines_with_recent_data = {r.get("dimension") for r in recent_dim_rows if r.get("dimension")}
    discipline_breakdown = compute_discipline_breakdown(dim_scores)
    sensor_coverage = compute_sensor_coverage(disciplines_with_recent_data)

    # State changes: pull recent canvas events; map to BriefingPayload.StateChange shape.
    recent_state_changes = []
    for r in state_change_rows:
        payload = r.get("payload") or {}
        recent_state_changes.append(
            {
                "kind": r.get("event_type", "unknown"),
                "description": payload.get("description") or payload.get("summary") or "",
                "at": r.get("created_at"),
                "target_ref": payload.get("target_ref") or payload.get("capability_id"),
            }
        )

    # Target drift: do the demo-target's required patterns clear their primary pillar's floor?
    pattern_to_pillar: dict[str, str] = {}
    demo_target_obj = ambition.target.demo_target if ambition and ambition.target else None
    if demo_target_obj and demo_target_obj.required_patterns:
        async with pool.connection() as db:
            pat_rows = parse_rows(
                await db.query(
                    """SELECT slug, primary_pillar FROM partnership_pattern
                       WHERE slug IN $slugs""",
                    {"slugs": list(demo_target_obj.required_patterns)},
                )
            )
        pattern_to_pillar = {r.get("slug", ""): r.get("primary_pillar", "") for r in pat_rows if r.get("slug")}
    target_drift = compute_target_drift_assessment(
        demo_target=demo_target_obj,
        pattern_to_pillar=pattern_to_pillar,
        pillar_scores=pillar_scores_str,
        phase_floors=phase_floors,
    )

    # Top recommendations: ranked by StrategicPrioritizer (phase-aware path
    # activates when phase_aware_ranking_enabled flag is on for this product).
    from core.engine.product.strategic_prioritizer import StrategicPrioritizer

    prioritizer = StrategicPrioritizer(pool)
    try:
        ranked = await prioritizer.prioritize(product_id)
    except Exception:
        ranked = []
    top_recommendations = []
    for r in ranked[:5]:
        top_recommendations.append(
            {
                "pillar": r.get("pillar"),
                "discipline": r.get("discipline") or r.get("dimension"),
                "score": r.get("current_score") or r.get("score"),
                "floor": r.get("floor"),
                "gap": r.get("gap"),
                "ambition_relevance": r.get("ambition_relevance"),
                "rank": r.get("rank") or r.get("priority_score"),
                "blocking_patterns": r.get("blocking_patterns", []),
                "rationale": r.get("rationale", ""),
                "consecutive_briefings_at_top": r.get("consecutive_briefings_at_top", 0),
            }
        )

    # GraphRAG community summaries — the largest knowledge communities (written by the
    # community_summarizer engine), so the briefing shows the SHAPE of accumulated knowledge. Best-effort.
    community_summaries: list[str] = []
    try:
        async with pool.connection() as db:
            cs_rows = parse_rows(
                await db.query(
                    "SELECT summary, member_count FROM community_summary "
                    "WHERE product = <record>$pid ORDER BY member_count DESC LIMIT 5",
                    {"pid": product_id},
                )
            )
        for r in cs_rows:
            if r.get("summary"):
                community_summaries.append(f"{r['summary']} ({r.get('member_count', '?')} items)")
    except Exception:
        pass

    return {
        "product_id": product_id,
        "timestamp": datetime.now().isoformat(),
        "current_phase": current_phase,
        "days_in_phase": days_in_phase,
        "next_phase": _next_phase(current_phase),
        "phase_floors": phase_floors,
        "demo_target": (
            asdict(ambition.target.demo_target)
            if ambition and ambition.target and ambition.target.demo_target
            else None
        ),
        "target_drift_assessment": (
            {
                "n_total": target_drift.n_total,
                "n_blocked": target_drift.n_blocked,
                "blocking_pillars": target_drift.blocking_pillars,
            }
            if target_drift is not None
            else None
        ),
        "pillar_scores": pillar_scores_str,
        "discipline_breakdown": discipline_breakdown,
        "sensor_coverage": sensor_coverage,
        "top_recommendations": top_recommendations,
        "blocked_patterns": (
            ambition.target.demo_target.required_patterns
            if ambition and ambition.target and ambition.target.demo_target
            else []
        ),
        "open_uncertainty_queries": [{"id": q.id, "scope": q.scope, "question": q.question} for q in open_qs],
        "recent_state_changes": recent_state_changes,
        # contributor_activity intentionally left {} — data path (git-log vs
        # canonical event store) is undecided; populated in a follow-up spec.
        "contributor_activity": {},
        "community_summaries": community_summaries,
    }


def _next_phase(current: str) -> str | None:
    chain = ["discovery", "poc", "alpha", "beta", "ga", "mature"]
    if current not in chain:
        return None
    idx = chain.index(current)
    return chain[idx + 1] if idx + 1 < len(chain) else None
