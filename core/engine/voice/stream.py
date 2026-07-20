"""Voice stream — bus subscriber that turns canvas events into ProactiveLines."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from core.engine.notifications.audit_buffer import record
from core.engine.proactive.models import ProactiveLine, ProactiveSource
from core.engine.voice.audit import audit_or_warn
from core.engine.voice.dispatch import VoiceDispatch
from core.engine.voice.renderers import (
    render_drift,
    render_recommendation,
    render_state_change,
    render_uncertainty,
)

logger = logging.getLogger(__name__)

_PRIORITY_RANK: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def should_emit(
    candidate: ProactiveLine,
    recent_history: list[ProactiveLine],
    threshold: Literal["LOW", "MEDIUM", "HIGH"] = "LOW",
) -> bool:
    """v1 gate: priority threshold + topic-per-day dedup. Legacy lines bypass."""
    if candidate.priority is None:
        return True
    if _PRIORITY_RANK[candidate.priority] < _PRIORITY_RANK[threshold]:
        return False
    today = datetime.now(timezone.utc).date()
    same_topic_today = any(
        h.topic and h.topic == candidate.topic and h.generated_at.date() == today for h in recent_history
    )
    return not same_topic_today


def _topic_for(event_type: str, payload: dict) -> str:
    if event_type == "canvas.drift.crossed":
        return "drift"
    if event_type == "canvas.recommendation.shifted":
        return f"rec:{payload.get('top_pillar', '')}.{payload.get('top_discipline', '')}"
    if event_type in ("canvas.uncertainty.opened", "canvas.uncertainty.answered"):
        return f"uncertainty:{payload.get('query_id', '?')}"
    if event_type == "canvas.decision.captured":
        return f"decision:{payload.get('decision_id', '?')}"
    if event_type == "canvas.capability.added":
        return f"capability:{payload.get('capability_id', '?')}"
    if event_type == "canvas.capability.lifecycle_changed":
        return f"capability:{payload.get('capability_id', '?')}:lifecycle"
    if event_type == "canvas.sentinel.fired":
        return f"sentinel:{payload.get('sentinel_name', '?')}"
    if event_type.startswith("canvas.handoff."):
        return f"handoff:{payload.get('handoff_id', '?')}"
    return event_type


def _dispatch_to_voice(event_type: str, payload: dict) -> VoiceDispatch | None:
    """Return a deferred VoiceDispatch for the event, or None if not voice-rendered.

    v2 inversion: caller receives the renderer + render_input and is responsible for
    building RenderContext (with thread state) before invoking renderer(render_input, ctx).
    """
    # Detector-only — never directly voice-rendered:
    if event_type in (
        "canvas.score.changed",
        "canvas.capability.updated",
        "canvas.edge.added",
        "canvas.briefing.updated",
        "canvas.proactive.line.updated",
        "canvas.handoff.progress",
    ):
        return None

    if event_type == "canvas.drift.crossed":
        from core.engine.product.briefing_payload import TargetDriftAssessment

        drift = TargetDriftAssessment(
            n_total=int(payload.get("n_total", 0)),
            n_blocked=int(payload.get("n_blocked", 0)),
            blocking_pillars=list(payload.get("blocking_pillars") or []),
        )
        return VoiceDispatch(
            renderer=render_drift,
            render_input=drift,
            priority="HIGH",
            topic=_topic_for(event_type, payload),
            thread_bearing=False,
        )

    if event_type == "canvas.recommendation.shifted":
        rec = payload.get("rec") or {
            "pillar": payload.get("top_pillar", ""),
            "discipline": payload.get("top_discipline", ""),
            "gap": float(payload.get("top_rank_score", 0.0)),
            "blocking_patterns": [],
        }
        priority = "HIGH" if payload.get("swap") else "MEDIUM"
        return VoiceDispatch(
            renderer=render_recommendation,
            render_input=rec,
            priority=priority,
            topic=_topic_for(event_type, payload),
            thread_bearing=True,
        )

    if event_type == "canvas.uncertainty.opened":
        return VoiceDispatch(
            renderer=render_uncertainty,
            render_input=payload,
            priority="HIGH",
            topic=_topic_for(event_type, payload),
            thread_bearing=False,
        )
    if event_type == "canvas.uncertainty.answered":
        return VoiceDispatch(
            renderer=render_uncertainty,
            render_input=payload,
            priority="LOW",
            topic=_topic_for(event_type, payload),
            thread_bearing=False,
        )

    if event_type in (
        "canvas.decision.captured",
        "canvas.capability.added",
        "canvas.capability.lifecycle_changed",
        "canvas.sentinel.fired",
        "canvas.handoff.started",
        "canvas.handoff.completed",
    ):
        sc = {
            "kind": event_type,
            "description": payload.get("description", ""),
            "target_ref": payload.get("target_ref"),
        }
        priority_map = {
            "canvas.decision.captured": "MEDIUM",
            "canvas.capability.added": "LOW",
            "canvas.capability.lifecycle_changed": "MEDIUM",
            "canvas.sentinel.fired": "MEDIUM",
            "canvas.handoff.started": "MEDIUM",
            "canvas.handoff.completed": "LOW",
        }
        return VoiceDispatch(
            renderer=render_state_change,
            render_input=sc,
            priority=priority_map[event_type],
            topic=_topic_for(event_type, payload),
            thread_bearing=False,
        )

    if event_type == "canvas.intelligence.classified":
        discipline = payload.get("discipline", "unknown")
        sc = {
            "kind": event_type,
            "description": payload.get("summary", f"Intelligence classified: {discipline}"),
            "target_ref": None,
        }
        return VoiceDispatch(
            renderer=render_state_change,
            render_input=sc,
            priority="LOW",
            topic=f"intelligence:{discipline}",
            thread_bearing=False,
        )

    if event_type == "canvas.pattern.matched":
        pattern_slug = payload.get("pattern_slug", "unknown")
        sc = {
            "kind": event_type,
            "description": payload.get("description", f"Pattern matched: {pattern_slug}"),
            "target_ref": None,
        }
        return VoiceDispatch(
            renderer=render_state_change,
            render_input=sc,
            priority="LOW",
            topic=f"pattern:{pattern_slug}",
            thread_bearing=False,
        )

    return None


async def emit_proactive_line(
    event_type: str,
    payload: dict,
    recent_history: list[ProactiveLine],
) -> ProactiveLine | None:
    """Bus event → ProactiveLine candidate, or None when not voice-relevant.

    v2 orchestration:
      1. _dispatch_to_voice → VoiceDispatch | None
      2. For thread_bearing events: look up/create VoiceThread (gated by feature flag),
         build RenderContext with thread state, salience policy, fresh payload hash.
      3. renderer(render_input, ctx) → line_text | None
      4. Anti-pattern gates: exact_phrase_repetition, over_reference.
         Blocked → write voice_audit row, write re_referenced event (emitted=false), return None.
      5. should_emit v1 gate.
      6. Build ProactiveLine, write re_referenced event (emitted=true), update thread state.
    """
    dispatch = _dispatch_to_voice(event_type, payload)
    if dispatch is None:
        return None

    product_id = payload.get("product_id", "product:platform")

    # --- Build RenderContext ---
    from core.engine.voice.render_context import RenderContext

    ctx = RenderContext(recent_emissions=list(recent_history))

    if dispatch.thread_bearing:
        try:
            from core.engine.core.db import pool
            from core.engine.voice.feature_flag import is_voice_continuity_enabled
            from core.engine.voice.hashing import compute_payload_hash
            from core.engine.voice.salience import policy_for_pillar
            from core.engine.voice.thread import _ensure_thread

            fresh_hash = compute_payload_hash(event_type, payload)
            ctx.fresh_payload_hash = fresh_hash

            if await is_voice_continuity_enabled(pool, product_id):
                thread = await _ensure_thread(product_id, dispatch.topic, event_type)
                pillar = (payload.get("rec") or payload).get("top_pillar") or payload.get("top_pillar", "")
                if not pillar and isinstance(dispatch.render_input, dict):
                    pillar = dispatch.render_input.get("pillar", "")
                ctx.thread = thread
                ctx.salience_policy = policy_for_pillar(pillar)
        except Exception as exc:
            logger.debug("emit_proactive_line: thread lookup failed (non-fatal): %s", exc)

    # --- Render ---
    line_text = dispatch.renderer(dispatch.render_input, ctx)
    if line_text is None:
        logger.debug("emit_proactive_line: renderer suppressed output for %s", event_type)
        return None

    # --- Anti-pattern gates (thread_bearing only when thread is live) ---
    if ctx.thread is not None:
        try:
            from core.engine.voice.anti_patterns import (
                detect_exact_phrase_repetition,
                detect_over_reference,
            )
            from core.engine.voice.thread_event import write_thread_event

            if detect_exact_phrase_repetition(line_text, recent_history):
                await _write_voice_audit(product_id, ctx.thread, "exact_phrase_repetition", line_text)
                await write_thread_event(
                    ctx.thread,
                    kind="re_referenced",
                    details={"emitted": False, "blocked_by": "exact_phrase_repetition"},
                )
                return None

            if await detect_over_reference(ctx.thread):
                await _write_voice_audit(product_id, ctx.thread, "over_reference", line_text)
                await write_thread_event(
                    ctx.thread, kind="re_referenced", details={"emitted": False, "blocked_by": "over_reference"}
                )
                return None
        except Exception as exc:
            logger.debug("emit_proactive_line: anti-pattern check failed (non-fatal): %s", exc)

    # --- v1 should_emit gate ---
    candidate = ProactiveLine(
        product_id=product_id,
        line=line_text,
        source=ProactiveSource.SENTINEL,
        source_artifact_id=payload.get("source_artifact_id", event_type),
        drill_down_url=payload.get("drill_down_url", "/"),
        severity=float(payload.get("severity", 0.5)),
        generated_at=datetime.now(timezone.utc),
        priority=dispatch.priority,
        topic=dispatch.topic,
    )
    if not should_emit(candidate, recent_history):
        return None

    # --- Write thread state on clean emit ---
    if ctx.thread is not None:
        try:
            from core.engine.core.db import pool
            from core.engine.voice.thread_event import write_thread_event

            await write_thread_event(ctx.thread, kind="re_referenced", details={"emitted": True})
            async with pool.connection() as db:
                await db.query(
                    """UPDATE <record>$tid SET
                        mention_count = mention_count + 1,
                        last_referenced_at = time::now(),
                        current_payload_hash = <string>$h
                    """,
                    {"tid": ctx.thread.id, "h": ctx.fresh_payload_hash or ""},
                )
        except Exception as exc:
            logger.debug("emit_proactive_line: thread state update failed (non-fatal): %s", exc)

    audit_or_warn(line_text, label="proactive_line")
    record("proactive_line", product_id, line_text)

    return candidate


async def _write_voice_audit(
    product_id: str,
    thread,
    kind: str,
    candidate_line: str,
    details: dict | None = None,
) -> None:
    """Write a voice_audit row for a suppressed line."""
    try:
        from core.engine.core.db import pool

        async with pool.connection() as db:
            await db.query(
                """CREATE voice_audit CONTENT {
                    product: <record>$pid,
                    thread: <record>$tid,
                    detected_at: time::now(),
                    kind: <string>$kind,
                    candidate_line: <string>$line,
                    details: $details
                }""",
                {
                    "pid": product_id,
                    "tid": thread.id,
                    "kind": kind,
                    "line": candidate_line,
                    "details": details or {},
                },
            )
    except Exception as exc:
        logger.debug("_write_voice_audit: failed (non-fatal): %s", exc)


async def _read_recent_proactive_history(product_id: str | None) -> list[ProactiveLine]:
    """Read today's ProactiveLines from event_log for dedup checking."""
    if not product_id:
        return []
    from core.engine.core.db import parse_rows, pool

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT payload, created_at FROM event_log
                   WHERE event_type = 'canvas.proactive.line'
                     AND product = $pid
                     AND created_at > time::now() - 1d
                   ORDER BY created_at DESC LIMIT 100""",
                {"pid": product_id},
            )
        )
    history: list[ProactiveLine] = []
    for r in rows:
        try:
            history.append(ProactiveLine(**r.get("payload", {})))
        except Exception:
            continue
    return history


async def _on_canvas_event(event_type: str, payload: dict) -> None:
    if not event_type.startswith("canvas."):
        return
    from core.engine.events.bus import bus

    history = await _read_recent_proactive_history(payload.get("product_id"))
    line = await emit_proactive_line(event_type, payload, history)
    if line is not None:
        await bus.emit("canvas.proactive.line", line.model_dump(mode="json"))


def register_voice_stream() -> None:
    """Register the wildcard bus subscriber + v2 transition subscribers. Called once at app startup."""
    from core.engine.events.bus import bus
    from core.engine.voice.transitions import register_voice_transitions

    bus.on("*", _on_canvas_event)
    register_voice_transitions()
