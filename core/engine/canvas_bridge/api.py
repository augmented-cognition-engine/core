"""FastAPI router for the canvas bridge — endpoints to trigger demos
and (later) for real orchestrator hooks. Phase 4 surface is intentionally
small: a single demo trigger that fires the scripted deliberation
defined in :mod:`core.engine.canvas_bridge.demo`.
"""

from __future__ import annotations

import asyncio
from logging import getLogger

from fastapi import APIRouter, BackgroundTasks

from core.engine.canvas_bridge.bridge import bridge
from core.engine.canvas_bridge.demo import run_scripted_deliberation

logger = getLogger(__name__)

router = APIRouter(prefix="/canvas/bridge", tags=["canvas-bridge"])


@router.post("/demo/deliberate/{room_id}")
async def trigger_scripted_deliberation(room_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Kick off a scripted Phase 4 deliberation in the given room.

    Returns immediately; the deliberation runs in the background and
    streams contributions into the room's Yjs doc over ~12 seconds.
    """
    background_tasks.add_task(_run_demo_safely, room_id)
    return {"status": "started", "room_id": room_id}


async def _run_demo_safely(room_id: str) -> None:
    try:
        await run_scripted_deliberation(room_id)
    except Exception:
        logger.exception("scripted deliberation failed for room=%s", room_id)


@router.post("/clear/{room_id}")
async def clear_room_agents(room_id: str) -> dict[str, str]:
    """Wipe agent contributions + cursors from a room. Useful between
    demo runs so the board doesn't accumulate stale shapes."""
    b = bridge()
    await asyncio.gather(
        b.clear_contributions(room_id),
        b.clear_all_cursors(room_id),
    )
    return {"status": "cleared", "room_id": room_id}
