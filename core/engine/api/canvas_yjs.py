"""Yjs WebSocket sync endpoint for the ACE canvas (Phase 3 of
``docs/superpowers/specs/2026-05-26-canvas-path-c-multiplayer-board.md``).

Mounts a y-websocket-protocol-compatible endpoint at::

    /canvas/ws/{room_id}

The frontend (``core/ui/canvas/src/app/board/persistence.ts``) attaches a
``y-websocket`` ``WebsocketProvider`` to this URL and the same Yjs ``Doc``
that ``y-indexeddb`` is already persisting locally. Two browser tabs to
the same ``room_id`` see each other's shape moves and (in Phase 4+)
agent-driven changes.

Server-side persistence uses :class:`pycrdt.store.FileYStore` — one file
per room under ``data/yjs/{room_id}.y``. ``data/`` is gitignored. Restart
preserves room state.

The pycrdt-websocket library ships an ASGI mount, but ACE's FastAPI app
already owns the routing surface. We adapt FastAPI's ``WebSocket`` to
pycrdt's ``Channel`` protocol directly so this endpoint participates in
the existing middleware/auth stack without a second sub-app.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from logging import getLogger
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pycrdt.store import FileYStore
from pycrdt.websocket import WebsocketServer, YRoom

logger = getLogger(__name__)

router = APIRouter()


# ── Storage location ─────────────────────────────────────────────────────────
# One file per room under data/yjs/. data/ is gitignored so this directory
# stays out of version control.
_REPO_ROOT = Path(__file__).resolve().parents[3]
STORE_DIR = _REPO_ROOT / "data" / "yjs"

# Conservative slug filter — room ids come from the URL path so keep this
# strict to avoid path traversal. Anything outside the allowed character
# set is replaced with `_`.
_ROOM_ID_SAFE = re.compile(r"[^A-Za-z0-9_\-]")


def _safe_room_filename(room_id: str) -> Path:
    safe = _ROOM_ID_SAFE.sub("_", room_id).strip("_") or "default"
    return STORE_DIR / f"{safe}.y"


# ── WebsocketServer subclass that injects FileYStore per room ────────────────


class FileBackedWebsocketServer(WebsocketServer):
    """A :class:`WebsocketServer` that gives every room a :class:`FileYStore`.

    The base class doesn't expose a per-room ``ystore`` hook; we override
    :meth:`get_room` and rebuild it. The body matches the base impl, with
    the only delta being the ystore injected into the YRoom constructor.
    """

    async def get_room(self, name: str) -> YRoom:
        if name not in self.rooms:
            store_path = _safe_room_filename(name)
            store_path.parent.mkdir(parents=True, exist_ok=True)
            ystore = FileYStore(str(store_path), log=self.log)
            self.rooms[name] = YRoom(
                ready=self.rooms_ready,
                log=self.log,
                ystore=ystore,
            )
        room = self.rooms[name]
        await self.start_room(room)
        return room


# ── Module-level singleton + lifespan hooks ──────────────────────────────────


_server: FileBackedWebsocketServer | None = None
_server_ctx: Any = None  # async-context manager from `async with server`


async def start_canvas_yjs_server() -> None:
    """Start the Yjs sync server; call from FastAPI lifespan startup.

    Idempotent — safe to call multiple times (subsequent calls are no-ops).
    """
    global _server, _server_ctx
    if _server is not None:
        return
    server = FileBackedWebsocketServer(
        rooms_ready=True,
        auto_clean_rooms=False,  # keep rooms hot across short reconnects
        log=logger,
    )
    # Enter the async context manager manually so the server's task group
    # outlives this coroutine. Stored in _server_ctx for clean shutdown.
    _server_ctx = server.__aenter__()
    await _server_ctx
    _server = server
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("canvas yjs sync server started (store=%s)", STORE_DIR)


async def stop_canvas_yjs_server() -> None:
    """Stop the Yjs sync server; call from FastAPI lifespan shutdown."""
    global _server, _server_ctx
    if _server is None:
        return
    try:
        await _server.__aexit__(None, None, None)
    finally:
        _server = None
        _server_ctx = None
    logger.info("canvas yjs sync server stopped")


# ── Channel adapter: FastAPI WebSocket → pycrdt Channel ──────────────────────


class _FastAPIWebSocketChannel:
    """Adapter exposing FastAPI's ``WebSocket`` as a pycrdt ``Channel``.

    pycrdt's protocol expects ``recv() -> bytes`` and ``send(bytes)``, plus
    a ``path`` attribute that becomes the room name. Async iteration is
    needed too — pycrdt iterates frames until disconnect.
    """

    def __init__(self, ws: WebSocket, path: str) -> None:
        self._ws = ws
        self.path = path

    async def recv(self) -> bytes:
        return await self._ws.receive_bytes()

    async def send(self, message: bytes) -> None:
        await self._ws.send_bytes(message)

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self.recv()
        except WebSocketDisconnect:
            raise StopAsyncIteration


# ── The actual endpoint ──────────────────────────────────────────────────────


@router.websocket("/canvas/ws/{room_id}")
async def canvas_yjs_websocket(websocket: WebSocket, room_id: str) -> None:
    """Bridge a browser y-websocket client into the pycrdt sync server.

    No auth on this endpoint yet — single-user dev mode per the Phase 3
    spec ("auth + room membership: out of scope for Phase 4"). Phase 6+
    will add JWT gating, matching the pattern in ``live_canvas.py``.
    """
    if _server is None:
        # Server didn't start (lifespan failure). Refuse cleanly.
        await websocket.close(code=1011, reason="canvas yjs server not running")
        return

    await websocket.accept()
    channel = _FastAPIWebSocketChannel(websocket, path=room_id)
    try:
        await _server.serve(channel)
    except WebSocketDisconnect:
        # Normal client close — nothing to do.
        pass
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("canvas yjs ws error (room=%s)", room_id)
        # Best-effort close; ignore failures if the socket is already gone.
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
