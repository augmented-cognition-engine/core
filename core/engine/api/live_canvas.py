"""Living Canvas WebSocket endpoint — real-time product model event stream.

Clients connect to /ws/canvas/{product_id} and receive LivingCanvasEvents
as JSON whenever the product model changes (capabilities, decisions, scores,
edges). Provenance is included with every event so the portal can render
"why this changed" alongside the change itself.

Connection flow:
  1. Client opens WebSocket to /ws/canvas/{product_id}?token={jwt}
  2. Server validates JWT, accepts connection
  3. If ?since_timestamp={iso} is given, server replays buffered events
  4. Server registers client for broadcast on canvas.* bus events
  5. Client receives events until disconnect

Replay buffer: last 60 seconds, in-process (not persisted). Clients that
missed > 60s should do a full HTTP fetch of current state instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["canvas"])

# ---------------------------------------------------------------------------
# Replay buffer — in-memory, per product_id, last 60 seconds
# ---------------------------------------------------------------------------

_REPLAY_WINDOW_SECONDS = 60
_MAX_BUFFER_PER_PRODUCT = 500


class _ReplayBuffer:
    """Ring buffer of recent canvas events per product_id."""

    def __init__(self) -> None:
        # product_id → deque of (emit_time, event_dict)
        self._buffers: dict[str, deque[tuple[datetime, dict]]] = {}

    def push(self, product_id: str, event: dict) -> None:
        buf = self._buffers.setdefault(product_id, deque(maxlen=_MAX_BUFFER_PER_PRODUCT))
        buf.append((datetime.now(timezone.utc), event))

    def since(self, product_id: str, since_dt: datetime) -> list[dict]:
        """Return events for product_id emitted at or after since_dt."""
        buf = self._buffers.get(product_id, deque())
        cutoff = since_dt
        return [evt for ts, evt in buf if ts >= cutoff]

    def prune(self, product_id: str) -> None:
        """Drop events older than the replay window."""
        buf = self._buffers.get(product_id)
        if not buf:
            return
        now = datetime.now(timezone.utc)
        while buf and (now - buf[0][0]).total_seconds() > _REPLAY_WINDOW_SECONDS:
            buf.popleft()


replay_buffer = _ReplayBuffer()


# ---------------------------------------------------------------------------
# Connection manager — product_id → list of active WebSocket connections
# ---------------------------------------------------------------------------


class CanvasConnectionManager:
    """Manages WebSocket connections grouped by product_id."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    def connect(self, product_id: str, ws: WebSocket) -> None:
        self._connections.setdefault(product_id, []).append(ws)
        logger.debug("Canvas client connected product=%s total=%d", product_id, len(self._connections[product_id]))

    def disconnect(self, product_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(product_id, [])
        if ws in conns:
            conns.remove(ws)
        logger.debug("Canvas client disconnected product=%s remaining=%d", product_id, len(conns))

    async def broadcast(self, product_id: str, message: dict) -> None:
        """Send message to all connected clients for this product_id."""
        text = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(product_id, [])):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(product_id, ws)

    def subscriber_count(self, product_id: str) -> int:
        return len(self._connections.get(product_id, []))


manager = CanvasConnectionManager()


# ---------------------------------------------------------------------------
# Bus handler — routes canvas.* events to WebSocket subscribers
# ---------------------------------------------------------------------------


def _register_canvas_bus_handler() -> None:
    """Register a wildcard bus handler that fans canvas events to WebSocket clients."""
    from core.engine.events.bus import bus

    async def _canvas_handler(event_type: str, payload: dict) -> None:
        if not event_type.startswith("canvas."):
            return
        product_id = payload.get("product_id", "")
        if not product_id:
            return
        # Buffer for replay
        replay_buffer.push(product_id, payload)
        replay_buffer.prune(product_id)
        # Broadcast to live clients
        await manager.broadcast(product_id, payload)

    bus.on("*", _canvas_handler)
    logger.info("Canvas bus handler registered")


# Called once at app startup
_register_canvas_bus_handler()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/canvas/{product_id}")
async def canvas_websocket(websocket: WebSocket, product_id: str) -> None:
    """Real-time product model event stream for the Living Canvas.

    Query params:
      token          — JWT (required)
      since_timestamp — ISO 8601; if provided, replay buffered events first
    """
    import jwt

    from core.engine.core.config import settings

    # Authenticate
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
    manager.connect(product_id, websocket)

    # Replay missed events
    since_raw = websocket.query_params.get("since_timestamp")
    if since_raw:
        try:
            since_dt = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
            missed = replay_buffer.since(product_id, since_dt)
            for evt in missed:
                await websocket.send_text(json.dumps(evt))
        except Exception as exc:
            logger.debug("Canvas replay failed (non-fatal): %s", exc)

    try:
        # Keep connection alive — we only push, never pull
        while True:
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.disconnect(product_id, websocket)
