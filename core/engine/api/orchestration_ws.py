"""Orchestration WebSocket — streams pipeline execution tree per canvas session.

Separate from /sessions/{id}/stream (canvas state WS).
This channel carries pipeline events: blocks, LLM consultations, ATC events.

Client → server: { type: "message"|"cancel"|"resume", ... }
Server → client: typed events from EventBus + hello/heartbeat frames
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.engine.core.db import parse_one
from core.engine.core.db import pool as default_pool
from core.engine.core.tasks import logged_task
from core.engine.orchestration.context import reset_active_bus, set_active_bus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["orchestration-ws"])

# In-memory registry: run_id → EventBus (for cancel lookup)
_active_buses: dict[str, object] = {}


async def _handle_connection(websocket: WebSocket, session_id: str) -> None:
    """Handle a single orchestration WS connection lifecycle."""

    product_id = "product:platform"
    try:
        async with default_pool.connection() as db:
            result = await db.query(
                "SELECT project_id FROM canvas_session WHERE id = <record>$sid LIMIT 1",
                {"sid": session_id},
            )
        row = parse_one(result)
        if row:
            product_id = row.get("project_id", product_id)
    except Exception:
        logger.warning("Could not load session %s for orchestration WS", session_id, exc_info=True)

    await websocket.send_json(
        {
            "type": "hello",
            "session_id": session_id,
            "product_id": product_id,
            "active_runs": [],
        }
    )

    heartbeat_task = asyncio.create_task(_heartbeat(websocket))

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                # decision:znalk48vc0rluxl1ejdg — logged_task so handler
                # exceptions land in error_buffer instead of vanishing.
                logged_task(
                    _handle_user_message(websocket, session_id, product_id, data),
                    label="orchestration_ws.user_message",
                )

            elif msg_type == "cancel":
                run_id = data.get("run_id", "")
                bus = _active_buses.get(run_id)
                if bus:
                    from core.engine.orchestration.events import RunCancelled

                    await bus.emit(RunCancelled(run_id=run_id, product_id=product_id))

            elif msg_type == "resume":
                run_id = data.get("run_id", "")
                last_seq = int(data.get("last_seq") or 0)
                await _replay(websocket, run_id, last_seq)

    except (WebSocketDisconnect, Exception) as exc:
        if not isinstance(exc, WebSocketDisconnect):
            logger.warning("Orchestration WS error for session %s: %s", session_id, exc)
    finally:
        heartbeat_task.cancel()


async def _heartbeat(websocket: WebSocket) -> None:
    """Send ping every 15s."""
    try:
        while True:
            await asyncio.sleep(15)
            await websocket.send_json({"type": "ping"})
    except Exception:
        pass


async def _handle_user_message(
    websocket: WebSocket,
    session_id: str,
    product_id: str,
    data: dict,
) -> None:
    """Route a user message through the pipeline, streaming events to WS."""
    from core.engine.canvas.conversation import save_message, save_turn
    from core.engine.orchestration.events import EventBus, RunDone, RunError, RunStart

    content = data.get("content", "")
    run_id = f"run_{uuid.uuid4().hex[:12]}"

    user_msg_id = await save_message(
        session_id=session_id,
        role="user",
        content=content,
        run_id=run_id,
    )

    bus = EventBus(run_id=run_id, product_id=product_id, persist_events=True)
    _active_buses[run_id] = bus
    _ctx_token = set_active_bus(bus)

    event_iter = await bus.subscribe()
    forward_task = asyncio.create_task(_forward_events(websocket, event_iter))

    await bus.emit(
        RunStart(
            run_id=run_id,
            product_id=product_id,
            session_id=session_id,
            user_message=content[:200],
        )
    )

    synthesis_content = ""
    decision_ids: list[str] = []

    try:
        from core.engine.canvas.canvas_ui_events import translate_canvas_event
        from core.engine.canvas.orchestrated_renderer import render_via_orchestration
        from core.engine.orchestrator.loader import load_intelligence

        # Bridge the renderer's rich reasoning events (per-perspective spins +
        # synthesis) into the UI protocol the frontend projects, forwarded on
        # the same per-run bus so they serialize with run_start/run_done.
        async def _on_canvas_event(event_type: str, event_payload: dict) -> None:
            ui_event = translate_canvas_event(event_type, event_payload, run_id=run_id, product_id=product_id)
            if ui_event is not None:
                await bus.emit(ui_event)

        _calibration: dict[str, float] = {}
        try:
            _loaded = await load_intelligence(discipline="", product_id=product_id, mode="reactive")
            _calibration = _loaded.get("calibration_weights", {})
        except Exception:
            # decision:745gfam2914vid6il7vt — silent calibration failure degrades
            # archetype weighting to the default (empty dict), making engagements
            # invisible-quality-degraded. Log at WARNING (degradation, not fatal).
            logger.warning(
                "Calibration load failed for product=%s — engagement will run with empty weights",
                product_id,
                exc_info=True,
            )

        result = await render_via_orchestration(
            kind="strategy",
            prompt=content,
            cited_text=[],
            prior_decisions=None,
            product_id=product_id,
            on_canvas_event=_on_canvas_event,
            event_bus=bus,
            calibration_weights=_calibration,
        )
        if result:
            synthesis_content = getattr(result, "synthesis", "") or ""

        await bus.emit(RunDone(run_id=run_id, product_id=product_id, duration_ms=0))

    except Exception as exc:
        await bus.emit(
            RunError(
                run_id=run_id,
                product_id=product_id,
                error=str(exc)[:200],
                recovery_hint="retry or rephrase your message",
            )
        )
    finally:
        reset_active_bus(_ctx_token)
        await bus.close()
        forward_task.cancel()
        _active_buses.pop(run_id, None)

    if synthesis_content:
        synth_msg_id = await save_message(
            session_id=session_id,
            role="ace",
            content=synthesis_content,
            run_id=run_id,
        )
        await save_turn(
            session_id=session_id,
            run_id=run_id,
            user_message_id=user_msg_id or "",
            synthesis_message_id=synth_msg_id,
            decision_ids=decision_ids,
        )


async def _forward_events(websocket: WebSocket, event_iter) -> None:
    """Forward EventBus events to the WS client as JSON."""
    try:
        async for event in event_iter:
            try:
                await websocket.send_json(event.to_dict())
            except Exception:
                break
    except asyncio.CancelledError:
        pass


async def _replay(websocket: WebSocket, run_id: str, last_seq: int) -> None:
    """Replay run_event rows with seq > last_seq for reconnect (per-event cursor)."""
    try:
        from core.engine.core.db import parse_rows

        async with default_pool.connection() as db:
            result = await db.query(
                "SELECT * FROM run_event WHERE run_id = $run_id AND seq > $last_seq ORDER BY seq ASC",
                {"run_id": run_id, "last_seq": last_seq},
            )
        rows = parse_rows(result)

        await websocket.send_json(
            {"type": "replay_start", "run_id": run_id, "from_seq": last_seq, "event_count": len(rows)}
        )
        for row in rows:
            payload = row.get("payload", {})
            await websocket.send_json(
                {
                    **payload,
                    "type": row.get("type"),
                    "run_id": row.get("run_id"),
                    "task_id": row.get("task_id"),
                    "parent_id": row.get("parent_id"),
                    "seq": row.get("seq"),
                    "ts": str(row.get("ts", "")),
                }
            )
        await websocket.send_json({"type": "replay_done", "run_id": run_id})
    except Exception:
        logger.warning("Replay failed for run %s", run_id, exc_info=True)


@router.websocket("/canvas/sessions/{session_id:path}/orchestration")
async def orchestration_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    await _handle_connection(websocket, session_id)
