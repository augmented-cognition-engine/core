"""Proactive Line API — single ranked surface ACE initiates from.

GET  /proactive/{product_id}/current      → ProactiveLine | null
GET  /proactive/{product_id}/recent?n=10  → list[ProactiveLine]
WS   /ws/proactive/{product_id}           → live ProactiveLine updates
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from core.engine.core.auth import get_current_user
from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.proactive.aggregator import aggregate, compute_current
from core.engine.proactive.models import ProactiveLine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proactive"])

# In-memory TTL cache. Aggregate runs the Haiku voice transformer per candidate
# (gates × findings × gaps × signals × recommendation) sequentially, so a cold
# call routinely takes 25-30s. Sentinel runs at most every few minutes, so a
# 60s cache for the rendered ProactiveLines is well within freshness budget.
# WS trigger events explicitly invalidate to keep live updates instant.
_CACHE_TTL_SECONDS = 60.0
_current_cache: dict[str, tuple[float, ProactiveLine | None]] = {}
_aggregate_cache: dict[str, tuple[float, list[ProactiveLine]]] = {}


def invalidate_proactive_cache(product_id: str) -> None:
    """Drop cached lines for this product. Called by canvas event handlers."""
    _current_cache.pop(product_id, None)
    _aggregate_cache.pop(product_id, None)


@router.get("/proactive/{product_id}/current")
async def get_current(
    product_id: str,
) -> ProactiveLine | None:
    """Return the single highest-priority partner-voice line, or null."""
    now = time.monotonic()
    cached = _current_cache.get(product_id)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    # Note: aggregate() manages its own short-lived DB leases internally,
    # so this endpoint does not wrap the call in a pool.connection() block.
    # Holding a connection for the entire 25-30s aggregate (gather+LLM
    # transforms) was saturating the 10-connection pool and forcing
    # unrelated GETs (e.g. /canvas/sessions) to queue 18-84 seconds.
    ranked = await aggregate(product_id)
    line = ranked[0] if ranked else None
    _current_cache[product_id] = (now, line)
    return line


@router.get("/proactive/{product_id}/recent")
async def get_recent(
    product_id: str,
    n: int = 10,
    user: dict = Depends(get_current_user),
) -> list[ProactiveLine]:
    """Return the top-n ranked ProactiveLines (all sources, ranked)."""
    now = time.monotonic()
    cached = _aggregate_cache.get(product_id)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1][:n]
    ranked = await aggregate(product_id)
    _aggregate_cache[product_id] = (now, ranked)
    return ranked[:n]


@router.websocket("/ws/proactive/{product_id}")
async def proactive_websocket(websocket: WebSocket, product_id: str) -> None:
    """Live ProactiveLine updates — pushes a new line when sentinel fires or gate changes."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except Exception:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    # Subscribe to canvas events that should trigger a new proactive line
    from core.engine.events.bus import bus

    trigger_events = {
        "canvas.score.changed",
        "canvas.capability.added",
        "canvas.decision.captured",
        "canvas.sentinel.fired",
    }
    triggered = asyncio.Event()

    async def _on_canvas_event(event_type: str, payload: dict) -> None:
        if payload.get("product_id") == product_id:
            invalidate_proactive_cache(product_id)
            triggered.set()

    for evt in trigger_events:
        bus.on(evt, _on_canvas_event)

    try:
        # Send current line immediately on connect
        async with pool.connection() as db:
            current = await compute_current(product_id, db)

        if current:
            await websocket.send_text(json.dumps(current.model_dump(mode="json"), default=str))

        while True:
            try:
                # Wait for a canvas trigger or ping timeout (30s)
                await asyncio.wait_for(triggered.wait(), timeout=30.0)
                triggered.clear()
            except asyncio.TimeoutError:
                # Ping keepalive
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue

            # Recompute and push updated line
            async with pool.connection() as db:
                updated = await compute_current(product_id, db)

            if updated:
                await websocket.send_text(json.dumps(updated.model_dump(mode="json"), default=str))

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        for evt in trigger_events:
            try:
                bus.off(evt, _on_canvas_event)
            except Exception:
                pass
