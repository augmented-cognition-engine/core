# engine/sentinel/engines/session_compressor.py
"""Session compressor engine — compress daily session traces into digests and insights.

Runs nightly at 2 AM. Reads the past 24h of session traces (task, observation,
orchestration_run, decision tables), groups by session_id, and produces:
1. A structured session_digest record per session.
2. Cross-session insight records via write_engine_insight().
3. Emits a session_digest.created event (best-effort).

Schema: session_digest is SCHEMALESS (schema v051).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import get_llm
from core.engine.sentinel.engines import write_engine_insight
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

SOURCE_DOMAIN = "sentinel.session-compressor"

DIGEST_PROMPT = """You are analyzing a session trace from an AI development system.

Extract a structured digest from the session activity below.

SESSION TRACE:
{trace}

Return JSON with exactly these fields:
{{
  "summary": "<1-3 sentence overview of what happened in this session>",
  "decisions": ["<decision made>", ...],
  "blockers": ["<blocker or impediment encountered>", ...],
  "outcomes": ["<concrete outcome or deliverable>", ...],
  "quality_signals": {{"<discipline>": <float -1.0 to 1.0>, ...}}
}}

Be concise. Empty objects/arrays are fine if a category has no entries."""

SYNTHESIS_PROMPT = """You are synthesizing insights across multiple development sessions.

SESSION DIGESTS:
{digests}

Identify 1-5 cross-session patterns, trends, or learnings that would improve future sessions.
Focus on recurring themes, systemic issues, or high-value practices.

Return a JSON array of insights:
[
  {{
    "content": "<the insight, actionable and specific>",
    "insight_type": "pattern|preference|correction|fact|procedure",
    "discipline": "<most relevant discipline: e.g. testing, architecture, security, ...>",
    "confidence": 0.0-1.0
  }},
  ...
]

Return an empty array [] if there are no meaningful cross-session insights."""


def _format_trace(trace_data: dict) -> str:
    """Format session trace as readable text with sections per record type."""
    lines = []

    tasks = trace_data.get("tasks", [])
    if tasks:
        lines.append("## Tasks")
        for t in tasks:
            desc = t.get("description", "")
            status = t.get("status", "")
            discipline = t.get("discipline", "")
            lines.append(f"- [{status}] {desc} (discipline: {discipline})")

    observations = trace_data.get("observations", [])
    if observations:
        lines.append("\n## Observations")
        for o in observations:
            content = o.get("content", "")
            itype = o.get("insight_type", "")
            lines.append(f"- [{itype}] {content}")

    runs = trace_data.get("orchestration_runs", [])
    if runs:
        lines.append("\n## Orchestration Runs")
        for r in runs:
            pattern = r.get("pattern", "")
            status = r.get("status", "")
            discipline = r.get("discipline", r.get("domain_path", ""))
            lines.append(f"- [{status}] pattern={pattern} discipline={discipline}")

    decisions = trace_data.get("decisions", [])
    if decisions:
        lines.append("\n## Decisions")
        for d in decisions:
            title = d.get("title", "")
            rationale = d.get("rationale", "")
            lines.append(f"- {title}: {rationale}")

    return "\n".join(lines) if lines else "(empty session)"


def _validate_session_compressor_inputs(product_id: str, budget: int = 100) -> None:
    """Validate session compressor inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for session-compressor: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="session_compressor",
    cron="0 2 * * *",
    description="Compress daily session traces into digests and insights",
)
async def run_session_compressor(product_id: str) -> dict:
    """Read past 24h of session data, write digests and cross-session insights.

    Args:
        product_id: Organization to process sessions for.

    Returns:
        Dict with sessions_processed, digests_written, insights_written.
    """
    sessions_processed = 0
    digests_written = 0
    insights_written = 0

    llm = get_llm()

    _validate_session_compressor_inputs(product_id)
    # ── Pass 0: Fetch all records from past 24h ───────────────────────────────
    async with pool.connection() as db:
        task_result = await db.query(
            "SELECT * FROM task WHERE product = <record>$product AND created_at > time::now() - 1d",
            {"product": product_id},
        )
        tasks = parse_rows(task_result)

        obs_result = await db.query(
            "SELECT * FROM observation WHERE product = <record>$product AND created_at > time::now() - 1d",
            {"product": product_id},
        )
        observations = parse_rows(obs_result)

        run_result = await db.query(
            "SELECT * FROM orchestration_run WHERE product = <record>$product AND created_at > time::now() - 1d",
            {"product": product_id},
        )
        orch_runs = parse_rows(run_result)

        dec_result = await db.query(
            "SELECT * FROM decision WHERE product = <record>$product AND created_at > time::now() - 1d",
            {"product": product_id},
        )
        decisions = parse_rows(dec_result)

    # ── Group by session_id ───────────────────────────────────────────────────
    session_map: dict[str, dict] = {}

    def _bucket(record: dict, key: str) -> None:
        sid = record.get("session_id") or "unknown"
        if sid not in session_map:
            session_map[sid] = {"tasks": [], "observations": [], "orchestration_runs": [], "decisions": []}
        session_map[sid][key].append(record)

    for t in tasks:
        _bucket(t, "tasks")
    for o in observations:
        _bucket(o, "observations")
    for r in orch_runs:
        _bucket(r, "orchestration_runs")
    for d in decisions:
        _bucket(d, "decisions")

    if not session_map:
        return {
            "sessions_processed": 0,
            "digests_written": 0,
            "insights_written": 0,
        }

    # Compute period string for this run (YYYY-MM-DD of today)
    period = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Pass 1: Per-session digest ────────────────────────────────────────────
    all_digests: list[dict] = []

    for session_id, trace_data in session_map.items():
        trace_text = _format_trace(trace_data)
        prompt = DIGEST_PROMPT.format(trace=trace_text)

        try:
            digest = await llm.complete_json(prompt)
        except Exception as exc:
            logger.warning("Digest generation failed for session %s: %s", session_id, exc)
            continue

        if not isinstance(digest, dict):
            logger.warning("Unexpected digest format for session %s: %r", session_id, digest)
            continue

        # Derive per-session metadata from trace
        session_tasks = trace_data.get("tasks", [])
        disciplines_touched = list({t.get("discipline", "") for t in session_tasks if t.get("discipline")})

        # Write digest record
        async with pool.connection() as db:
            try:
                await db.query(
                    """CREATE session_digest SET
                        session_id = $session_id,
                        period = $period,
                        summary = $summary,
                        decisions = $decisions,
                        blockers = $blockers,
                        outcomes = $outcomes,
                        quality_signals = $quality_signals,
                        tasks_executed = $tasks_executed,
                        disciplines_touched = $disciplines_touched,
                        intelligence_used = $intelligence_used,
                        created_at = time::now()""",
                    {
                        "product": product_id,
                        "session_id": session_id,
                        "period": period,
                        "summary": digest.get("summary", ""),
                        "decisions": digest.get("decisions", []),
                        "blockers": digest.get("blockers", []),
                        "outcomes": digest.get("outcomes", []),
                        "quality_signals": digest.get("quality_signals", {}),
                        "tasks_executed": len(session_tasks),
                        "disciplines_touched": disciplines_touched,
                        "intelligence_used": [],
                    },
                )
                digests_written += 1
            except Exception as exc:
                logger.warning("Failed to write session_digest for %s: %s", session_id, exc)

        all_digests.append({"session_id": session_id, **digest})
        sessions_processed += 1

    # ── Pass 2: Cross-session synthesis ──────────────────────────────────────
    if all_digests:
        digests_text = "\n\n".join(
            f"Session {d['session_id']}:\n"
            f"  Summary: {d.get('summary', '')}\n"
            f"  Decisions: {d.get('decisions', [])}\n"
            f"  Blockers: {d.get('blockers', [])}\n"
            f"  Outcomes: {d.get('outcomes', [])}\n"
            f"  Quality signals: {d.get('quality_signals', [])}"
            for d in all_digests
        )

        synthesis_prompt = SYNTHESIS_PROMPT.format(digests=digests_text)

        try:
            raw_insights = await llm.complete_json(synthesis_prompt)
            if isinstance(raw_insights, dict):
                raw_insights = [raw_insights]
        except Exception as exc:
            logger.warning("Cross-session synthesis failed: %s", exc)
            raw_insights = []

        if isinstance(raw_insights, list):
            async with pool.connection() as db:
                for insight_data in raw_insights:
                    if not isinstance(insight_data, dict):
                        continue
                    content = insight_data.get("content", "")
                    if not content:
                        continue
                    try:
                        insight_id = await write_engine_insight(
                            db,
                            product_id=product_id,
                            content=content,
                            insight_type=insight_data.get("insight_type", "pattern"),
                            tier="org",
                            discipline=insight_data.get("discipline", "architecture"),
                            source_domain=SOURCE_DOMAIN,
                            confidence=float(insight_data.get("confidence", 0.6)),
                            tags=["session_synthesis", insight_data.get("discipline", "architecture")],
                        )
                        if insight_id:
                            insights_written += 1
                    except Exception as exc:
                        logger.warning("Failed to write synthesis insight: %s", exc)

    # ── Emit event (best-effort) ──────────────────────────────────────────────
    try:
        from core.engine.events.bus import bus

        await bus.emit(
            "session_digest.created",
            {
                "product_id": product_id,
                "sessions_processed": sessions_processed,
                "digests_written": digests_written,
            },
        )
    except Exception:
        pass

    return {
        "sessions_processed": sessions_processed,
        "digests_written": digests_written,
        "insights_written": insights_written,
    }
