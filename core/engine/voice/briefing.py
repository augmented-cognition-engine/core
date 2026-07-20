"""Compose the morning briefing markdown from a BriefingPayload dict."""

from __future__ import annotations

import logging

from core.engine.voice.audit import audit_or_warn
from core.engine.voice.composition import (
    engine_footer,
    lede_paragraph,
    open_questions_section,
)
from core.engine.voice.feature_flag import is_voice_continuity_enabled
from core.engine.voice.renderers import render_drift, render_frame
from core.engine.voice.thread import read_voice_thread

logger = logging.getLogger(__name__)


def _next_phase_days(payload: dict) -> int | None:
    """Compute days-to-demo from demo_target.target_date if present."""
    demo = payload.get("demo_target")
    if not demo:
        return None
    from datetime import date, datetime

    raw = demo.get("target_date")
    if not raw:
        return None
    if isinstance(raw, datetime):
        target = raw.date()
    elif isinstance(raw, date):
        target = raw
    elif isinstance(raw, str):
        try:
            target = date.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    return (target - date.today()).days


async def _build_focus_section(
    top_recs: list[dict],
    product_id: str,
    n: int = 3,
) -> str:
    """Render top-N recommendations with thread-aware RenderContext (gated by feature flag).

    Falls back to v1 rendering (ctx=None) when voice continuity is disabled or thread lookup fails.
    """
    from core.engine.core.db import pool
    from core.engine.voice.hashing import compute_payload_hash
    from core.engine.voice.render_context import RenderContext
    from core.engine.voice.renderers import render_recommendation
    from core.engine.voice.salience import policy_for_pillar

    continuity_on = False
    try:
        continuity_on = await is_voice_continuity_enabled(pool, product_id)
    except Exception as exc:
        logger.debug("_build_focus_section: feature flag check failed: %s", exc)

    bullets: list[str] = []
    for rec in top_recs[:n]:
        ctx: RenderContext | None = None
        if continuity_on:
            try:
                pillar = rec.get("pillar", "")
                discipline = rec.get("discipline", "")
                topic = f"rec:{pillar}.{discipline}"
                fresh_hash = compute_payload_hash("canvas.recommendation.shifted", rec)
                thread = await read_voice_thread(product_id, topic)
                ctx = RenderContext(
                    thread=thread,
                    salience_policy=policy_for_pillar(pillar),
                    fresh_payload_hash=fresh_hash,
                )
            except Exception as exc:
                logger.debug("_build_focus_section: thread lookup failed (non-fatal): %s", exc)
                ctx = None

        body = render_recommendation(rec, ctx)
        if body is not None:
            bullets.append(f"- {body}")

    return "## Focus this week\n\n" + "\n".join(bullets)


async def compose_morning_briefing(
    payload: dict,
    engine_runs: list[dict] | None = None,
) -> str:
    """Render BriefingPayload-shaped dict into partner-voice markdown briefing."""
    product_id = payload.get("product_id", "product:platform")

    # 1. Frame
    frame = render_frame(
        phase=payload.get("current_phase", "discovery"),
        days_in_phase=int(payload.get("days_in_phase", 0)),
        days_to_demo=_next_phase_days(payload),
    )

    # 2. Drift (structured dict → dataclass-shaped object via SimpleNamespace)
    drift_dict = payload.get("target_drift_assessment")
    if drift_dict:
        from types import SimpleNamespace

        drift_ns = SimpleNamespace(**drift_dict)
        drift_str = render_drift(drift_ns)
    else:
        drift_str = ""

    # 3. Lede
    lede = lede_paragraph(frame, drift_str)

    # 4. Focus — thread-aware RenderContext per rec
    focus = await _build_focus_section(
        payload.get("top_recommendations") or [],
        product_id=product_id,
    )

    # 5. Open questions (conditional)
    qs_section = open_questions_section(payload.get("open_uncertainty_queries") or [])

    # 5b. Knowledge communities (GraphRAG) — the shape of what we've been accumulating knowledge around
    community_summaries = payload.get("community_summaries") or []
    community_section = None
    if community_summaries:
        lines = ["## Knowledge communities", "", "The shape of what we've been learning around:", ""]
        lines += [f"- {s}" for s in community_summaries[:5]]
        community_section = "\n".join(lines)

    # 6. Engine footer
    footer = engine_footer(engine_runs)

    parts = [lede, "", focus]
    if qs_section is not None:
        parts.extend(["", qs_section])
    if community_section is not None:
        parts.extend(["", community_section])
    parts.extend(["", footer])
    md = "\n".join(parts)

    audit_or_warn(md, label="morning_briefing")
    return md
