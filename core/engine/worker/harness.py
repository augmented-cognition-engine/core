"""Harness context builder — single source of voice truth for CLI hooks.

Hooks call GET /harness/context which calls build_harness_context().
All partner-voice strings are generated here; hooks render, never compose.

Voice rules enforced inline:
- Use "we", "our", "us" — never "I" alone
- No forbidden system strings: Alert, Warning, Notification, [INFO], [ERROR]
- ≤200 chars per voice field
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.engine.worker.health import get_health_state
from core.engine.worker.models import HarnessContext

logger = logging.getLogger(__name__)


def _format_greeting(
    discipline: str,
    summary: str | None,
    open_thread: str | None,
    n_ideas: int,
) -> str:
    """Deterministic colleague-voice session opener. Follows voice rules without LLM."""
    if open_thread:
        msg = f"we picked up where we left off — {open_thread[:100]}."
    elif summary:
        msg = f"we're continuing {discipline} work — {summary[:80]}."
    elif n_ideas > 0:
        noun = "idea" if n_ideas == 1 else "ideas"
        msg = f"we have {n_ideas} {noun} ready whenever you are."
    else:
        msg = f"we're watching the {discipline} layer."
    return msg[:200]


def _format_status_pulse(discipline: str, n_ideas: int, n_decisions: int) -> str:
    """Status line string. Always starts with 'watching: {discipline}'."""
    parts = [f"watching: {discipline}"]
    if n_ideas > 0:
        parts.append(f"{n_ideas} {'idea' if n_ideas == 1 else 'ideas'} ready")
    if n_decisions > 0:
        parts.append(f"{n_decisions} recent {'decision' if n_decisions == 1 else 'decisions'}")
    return " · ".join(parts)


async def _get_session_state(session_id: str, product_id: str) -> dict:
    """Fetch session state from the worker session manager."""
    from core.engine.worker.session import session_manager

    return await session_manager.get_or_create(session_id, product_id)


async def _get_recent_decisions(product_id: str, db) -> list[dict]:
    from core.engine.core.db import parse_rows

    try:
        rows = parse_rows(
            await db.query(
                """SELECT title, decision_type, created_at
               FROM decision
               WHERE product = <record>$product AND status = 'active'
               ORDER BY created_at DESC LIMIT 3""",
                {"product": product_id},
            )
        )
        return [{"title": r.get("title", ""), "date": str(r.get("created_at", ""))[:10]} for r in rows]
    except Exception:
        return []


async def _get_active_ideas_count(product_id: str, db) -> int:
    from core.engine.core.db import parse_rows

    try:
        rows = parse_rows(
            await db.query(
                "SELECT count() AS n FROM idea WHERE product = <record>$product AND status = 'ready' GROUP ALL",
                {"product": product_id},
            )
        )
        return int(rows[0].get("n", 0)) if rows else 0
    except Exception:
        return 0


async def _get_proactive_line(product_id: str, db) -> tuple[str | None, str | None]:
    """Return (line_text, drill_down_url) or (None, None) if nothing to surface."""
    try:
        from core.engine.proactive.aggregator import compute_current

        pl = await compute_current(product_id, db)
        if pl:
            return pl.line, pl.drill_down_url
    except Exception as exc:
        logger.debug("proactive aggregator unavailable: %s", exc)
    return None, None


def _get_worker_health_warning() -> str | None:
    """Return a one-line warning when the hook pipeline is stale, else None."""
    state = get_health_state()
    if state.pipeline_status == "stale":
        idle_min = round((state.idle_seconds or 0) / 60)
        return f"our capture pipeline has been quiet for {idle_min}m — the post-tool hook may need a check"
    return None


async def build_harness_context(session_id: str, product_id: str) -> HarnessContext:
    """Build HarnessContext for hook consumption. Never raises."""
    # Computed before the try block — no I/O, never raises, must flow through both branches
    health_warning = _get_worker_health_warning()
    try:
        from core.engine.core.db import pool

        session_state = await _get_session_state(session_id, product_id)

        async with pool.connection() as db:
            decisions = await _get_recent_decisions(product_id, db)
            n_ideas = await _get_active_ideas_count(product_id, db)
            proactive_line, proactive_url = await _get_proactive_line(product_id, db)

        discipline = session_state.get("current_discipline") or (session_state.get("classification") or {}).get(
            "discipline", "architecture"
        )
        summary = session_state.get("rolling_summary") or None

        greeting = _format_greeting(discipline, summary, proactive_line, n_ideas)
        status_pulse = _format_status_pulse(discipline, n_ideas, len(decisions))

        return HarnessContext(
            session_id=session_id,
            product_id=product_id,
            greeting=greeting,
            status_pulse=status_pulse,
            proactive_line=proactive_line,
            proactive_drill_down=proactive_url,
            recent_decisions=decisions,
            worker_health=health_warning,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        logger.warning("build_harness_context failed, using fallback: %s", exc)
        return HarnessContext(
            session_id=session_id,
            product_id=product_id,
            greeting="we're watching the codebase.",
            status_pulse="watching: architecture",
            worker_health=health_warning,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
