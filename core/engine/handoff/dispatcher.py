"""Hand-Off dispatcher — lifecycle manager for agent dispatch.

Creates HandOff records, starts execution as a background task,
emits Living Canvas events, handles pause/resume/cancel.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from core.engine.core.tasks import logged_task
from core.engine.handoff.models import HandOff, HandOffProgressMessage, HandOffStatus
from core.engine.handoff.translators import translate

logger = logging.getLogger(__name__)

# In-memory store: active + recently completed handoffs
_HANDOFF_STORE: dict[str, HandOff] = {}
# Background tasks keyed by handoff_id
_HANDOFF_TASKS: dict[str, asyncio.Task] = {}
# Pause signals — set means "paused, wait before next batch"
_PAUSE_EVENTS: dict[str, asyncio.Event] = {}


async def dispatch(
    spec_id: str,
    agent: Literal["claude_code", "cursor", "codex", "lovable", "continue"],
    product_id: str,
    db_pool=None,
) -> HandOff:
    """Dispatch a spec to an agent. Returns immediately with HandOff (status=dispatched)."""
    handoff_id = str(uuid.uuid4())
    handoff = HandOff(
        id=handoff_id,
        product_id=product_id,
        spec_id=spec_id,
        agent=agent,
        status=HandOffStatus.DISPATCHED,
    )
    _HANDOFF_STORE[handoff_id] = handoff
    _PAUSE_EVENTS[handoff_id] = asyncio.Event()

    # Persist initial record
    if db_pool:
        try:
            async with db_pool.connection() as db:
                await db.query(
                    """CREATE handoff SET
                        id = $id,
                        product_id = <record>$product_id,
                        spec_id = $spec_id,
                        agent = $agent,
                        status = $status,
                        dispatched_at = $dispatched_at""",
                    {
                        "id": handoff_id,
                        "product_id": product_id,
                        "spec_id": spec_id,
                        "agent": agent,
                        "status": HandOffStatus.DISPATCHED.value,
                        "dispatched_at": handoff.dispatched_at.isoformat(),
                    },
                )
        except Exception as exc:
            logger.warning("Failed to persist handoff record (non-fatal): %s", exc)

    # Emit HANDOFF_STARTED canvas event
    try:
        from core.engine.events.canvas import emit_handoff_started

        await emit_handoff_started(
            product_id=product_id,
            handoff_id=handoff_id,
            spec_id=spec_id,
            agent=agent,
        )
    except Exception as exc:
        logger.warning("emit_handoff_started failed (non-fatal): %s", exc)

    # Start execution in background
    task = asyncio.create_task(
        _run_plan(handoff_id, spec_id, agent, product_id, db_pool),
        name=f"handoff:{handoff_id}",
    )
    _HANDOFF_TASKS[handoff_id] = task

    return handoff


async def pause(handoff_id: str) -> HandOff | None:
    """Signal the dispatcher to pause after the current batch."""
    handoff = _HANDOFF_STORE.get(handoff_id)
    if not handoff or handoff.status not in (HandOffStatus.DISPATCHED, HandOffStatus.RUNNING):
        return handoff
    handoff.status = HandOffStatus.PAUSED
    pause_evt = _PAUSE_EVENTS.get(handoff_id)
    if pause_evt:
        pause_evt.clear()
    return handoff


async def resume(handoff_id: str) -> HandOff | None:
    """Resume a paused handoff."""
    handoff = _HANDOFF_STORE.get(handoff_id)
    if not handoff or handoff.status != HandOffStatus.PAUSED:
        return handoff
    handoff.status = HandOffStatus.RUNNING
    pause_evt = _PAUSE_EVENTS.get(handoff_id)
    if pause_evt:
        pause_evt.set()
    return handoff


async def cancel(handoff_id: str) -> HandOff | None:
    """Cancel a running handoff within 5 seconds."""
    handoff = _HANDOFF_STORE.get(handoff_id)
    if not handoff:
        return None

    task = _HANDOFF_TASKS.get(handoff_id)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    handoff.status = HandOffStatus.CANCELLED
    handoff.completed_at = datetime.now(timezone.utc)
    return handoff


def get_handoff(handoff_id: str) -> HandOff | None:
    return _HANDOFF_STORE.get(handoff_id)


def _add_progress(handoff: HandOff, plain_language: str, raw_log: str | None, pct: int) -> None:
    msg = HandOffProgressMessage(
        plain_language=plain_language,
        raw_log_excerpt=raw_log,
        pct=pct,
    )
    handoff.progress_messages.append(msg)


async def _run_plan(
    handoff_id: str,
    spec_id: str,
    agent: str,
    product_id: str,
    db_pool,
) -> None:
    """Background task: load spec, run plan, emit progress, summarize."""
    handoff = _HANDOFF_STORE[handoff_id]
    handoff.status = HandOffStatus.RUNNING

    try:
        # Load plan from spec or synthesize a minimal one
        plan = await _load_plan(spec_id, product_id, db_pool)

        from core.engine.product.agent_orchestrator import AgentOrchestrator

        pause_evt = _PAUSE_EVENTS[handoff_id]

        async def _on_progress(progress: dict) -> None:
            """Called by orchestrator after each batch."""
            # Check pause gate between batches
            if handoff.status == HandOffStatus.PAUSED:
                await pause_evt.wait()

            pct = progress.get("pct", 0)
            completed = progress.get("completed", 0)
            total = progress.get("total", 0)
            failed = progress.get("failed", 0)

            if failed:
                raw = f"batch complete: {completed}/{total} done, {failed} failed"
                plain = translate(agent, raw)
            else:
                raw = f"batch complete: {completed}/{total} units done"
                plain = translate(agent, raw)

            _add_progress(handoff, plain, raw, pct)

            try:
                from core.engine.events.canvas import emit_handoff_progress

                # decision:znalk48vc0rluxl1ejdg — logged_task captures exceptions.
                logged_task(
                    emit_handoff_progress(product_id, handoff_id, plain, pct),
                    label="handoff.progress_emit",
                )
            except Exception:
                # Logged at WARNING so import-time failures aren't silent.
                logger.warning("Failed to schedule handoff progress emit", exc_info=True)

        orchestrator = AgentOrchestrator(db_pool=db_pool, on_progress=_on_progress)
        result = await orchestrator.execute_plan(plan, product_id=product_id)

        # Summarize completion
        from core.engine.handoff.summarizer import summarize

        summary = await summarize(result, agent)

        handoff.status = HandOffStatus.COMPLETED
        handoff.completed_at = datetime.now(timezone.utc)
        handoff.completion_summary = summary
        handoff.raw_result = result

        # Persist completion
        if db_pool:
            try:
                async with db_pool.connection() as db:
                    await db.query(
                        """UPDATE handoff SET
                            status = $status,
                            completed_at = $completed_at,
                            completion_summary = $summary
                           WHERE id = $id""",
                        {
                            "id": handoff_id,
                            "status": HandOffStatus.COMPLETED.value,
                            "completed_at": handoff.completed_at.isoformat(),
                            "summary": summary,
                        },
                    )
            except Exception as exc:
                logger.warning("Failed to persist handoff completion (non-fatal): %s", exc)

        try:
            from core.engine.events.canvas import emit_handoff_completed

            await emit_handoff_completed(
                product_id=product_id,
                handoff_id=handoff_id,
                status=HandOffStatus.COMPLETED.value,
                completion_summary=summary,
            )
        except Exception as exc:
            logger.warning("emit_handoff_completed failed (non-fatal): %s", exc)

    except asyncio.CancelledError:
        handoff.status = HandOffStatus.CANCELLED
        handoff.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        logger.error("HandOff %s failed: %s", handoff_id, exc)
        handoff.status = HandOffStatus.FAILED
        handoff.completed_at = datetime.now(timezone.utc)
        try:
            from core.engine.events.canvas import emit_handoff_completed

            await emit_handoff_completed(
                product_id=product_id,
                handoff_id=handoff_id,
                status=HandOffStatus.FAILED.value,
                completion_summary=f"We hit an error: {type(exc).__name__}. Want me to investigate?",
            )
        except Exception:
            pass


async def _load_plan(spec_id: str, product_id: str, db_pool) -> dict:
    """Load a plan from the spec record, or return a minimal stub plan."""
    if db_pool:
        try:
            from core.engine.core.db import parse_one

            async with db_pool.connection() as db:
                spec = parse_one(
                    await db.query(
                        "SELECT * FROM ONLY <record>$id LIMIT 1",
                        {"id": spec_id},
                    )
                )
            if spec and spec.get("plan"):
                return spec["plan"]
            if spec:
                return {
                    "spec_id": spec_id,
                    "units": [
                        {"id": "u1", "title": spec.get("title", spec_id), "description": spec.get("description", "")}
                    ],
                    "batches": [{"task_ids": ["u1"], "mode": "sequential"}],
                    "conflicts": [],
                }
        except Exception as exc:
            logger.warning("_load_plan DB query failed (non-fatal): %s", exc)

    return {
        "spec_id": spec_id,
        "units": [{"id": "u1", "title": spec_id, "description": f"Execute spec: {spec_id}"}],
        "batches": [{"task_ids": ["u1"], "mode": "sequential"}],
        "conflicts": [],
    }
