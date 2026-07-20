"""Canvas bridge — in-process API for agents to act on the board.

Mutates the shared ``Y.Doc`` for a given room. Updates propagate to all
connected browser clients via the Yjs WebSocket sync (Phase 3
infrastructure). The bridge is process-local; agents and the bridge
share memory with the WebsocketServer, so no socket round-trip is
needed when agents write.

Surface model — three Yjs structures per room:

  - ``Y.Map('board')['tldraw-snapshot']``  the human-edited tldraw state
  - ``Y.Array('agent_contributions')``      streaming agent voice writes
  - ``Y.Map('agent_cursors')``              transient cursor positions

The bridge writes to the latter two. The frontend observer in
``core/ui/canvas/src/app/board/agentSubscription.ts`` materializes the
agent_contributions array into tldraw shapes — keeping backend free of
tldraw record-format details.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from logging import getLogger

from pycrdt import Array, Doc, Map

from core.engine.canvas_bridge.messages import (
    AgentChatMessage,
)
from core.engine.canvas_bridge.messages import (
    clear_messages as _clear_messages,
)
from core.engine.canvas_bridge.messages import (
    observe_user_replies as _observe_user_replies,
)
from core.engine.canvas_bridge.messages import (
    post_message as _post_message,
)
from core.engine.canvas_bridge.participant import (
    AgentParticipant,
    get_participant,
)

logger = getLogger(__name__)


# Default starting positions on the board. Mirrors the frontend's
# LAYOUT constant in BoardSurface.tsx — agents drop into the same
# scatter the seed fixtures use, so a real deliberation looks at
# home next to fixture-seeded shapes.
DEFAULT_LAYOUT: dict[str, dict[str, int]] = {
    "architecture": {"x": 60, "y": 60, "w": 280, "h": 200},
    "security": {"x": 380, "y": 100, "w": 280, "h": 200},
    "data": {"x": 700, "y": 60, "w": 280, "h": 200},
    "ux": {"x": 220, "y": 360, "w": 280, "h": 240},
    "product_strategy": {"x": 540, "y": 380, "w": 280, "h": 160},
    "performance": {"x": 60, "y": 600, "w": 280, "h": 200},
    "ai_ml": {"x": 380, "y": 600, "w": 280, "h": 200},
    "partner": {"x": 980, "y": 220, "w": 280, "h": 200},
}


@dataclass
class AgentContribution:
    """Payload that lands in the ``agent_contributions`` Y.Array.

    Field names match :class:`~core/ui/canvas/src/app/state.ts`'s
    ``ContributionState`` so the frontend observer can pass values
    through unchanged. Optional fields default to ``None`` and are
    skipped in the wire dict via :meth:`to_dict` filtering.
    """

    id: str
    lens: str
    speaker: str
    accent: str
    framing: str
    in_flight: bool = False
    landed_at: str | None = None
    thinking_about: str | None = None
    x: int = 0
    y: int = 0
    w: int = 280
    h: int = 200

    def to_dict(self) -> dict[str, object]:
        # Convert in_flight → inFlight etc to match frontend camelCase.
        d = {
            "id": self.id,
            "lens": self.lens,
            "speaker": self.speaker,
            "accent": self.accent,
            "framing": self.framing,
            "inFlight": self.in_flight,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
        }
        if self.landed_at is not None:
            d["landedAt"] = self.landed_at
        if self.thinking_about is not None:
            d["thinkingAbout"] = self.thinking_about
        return d


@dataclass
class AgentCursor:
    """Payload that lands in the ``agent_cursors`` Y.Map under the
    agent id. Stretch feature — the frontend will render these as a
    custom overlay if it observes a non-empty map."""

    agent_id: str
    name: str
    accent: str
    glyph: str
    x: float
    y: float
    activity: str | None = None
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        if self.activity is None:
            d.pop("activity")
        return d


class CanvasBridge:
    """Process-level singleton that mutates shared Yjs docs for agents.

    Looks up the active :class:`~pycrdt.websocket.YRoom` from the
    :mod:`core.engine.api.canvas_yjs` server. If the room doesn't
    exist yet, it's created on demand (so an agent can warm the room
    before a human joins).
    """

    async def _get_doc(self, room_id: str) -> Doc:
        from core.engine.api import canvas_yjs

        if canvas_yjs._server is None:
            raise RuntimeError("canvas yjs server not running")
        room = await canvas_yjs._server.get_room(room_id)
        return room.ydoc

    # ── Agent contributions ─────────────────────────────────────────────

    async def add_contribution(self, room_id: str, contribution: AgentContribution) -> None:
        """Append a new contribution to the room.

        The frontend observer creates a new tldraw shape for this entry.
        Later updates to the same contribution should use
        :meth:`update_contribution` so the entry is replaced in place
        (frontend matches by id).
        """
        doc = await self._get_doc(room_id)
        contributions: Array = doc.get("agent_contributions", type=Array)
        with doc.transaction():
            contributions.append(contribution.to_dict())
        logger.info(
            "bridge: add_contribution room=%s lens=%s id=%s",
            room_id,
            contribution.lens,
            contribution.id,
        )

    async def update_contribution(
        self,
        room_id: str,
        contribution_id: str,
        *,
        framing: str | None = None,
        in_flight: bool | None = None,
        landed_at: str | None = None,
        thinking_about: str | None = None,
    ) -> bool:
        """Patch an existing contribution by id.

        Returns ``True`` if found and updated, ``False`` otherwise. Uses
        replace-in-place semantics (Yjs Arrays don't support mutation
        of nested dicts — must delete + insert at the same index).
        """
        doc = await self._get_doc(room_id)
        contributions: Array = doc.get("agent_contributions", type=Array)
        for i in range(len(contributions)):
            entry = contributions[i]
            if not isinstance(entry, dict):
                continue
            if entry.get("id") != contribution_id:
                continue
            patched = dict(entry)
            if framing is not None:
                patched["framing"] = framing
            if in_flight is not None:
                patched["inFlight"] = in_flight
            if landed_at is not None:
                patched["landedAt"] = landed_at
            if thinking_about is not None:
                patched["thinkingAbout"] = thinking_about
            with doc.transaction():
                del contributions[i]
                contributions.insert(i, patched)
            return True
        return False

    async def clear_contributions(self, room_id: str) -> None:
        """Wipe all agent contributions from the room — useful between
        demo runs so the board doesn't accumulate stale shapes."""
        doc = await self._get_doc(room_id)
        contributions: Array = doc.get("agent_contributions", type=Array)
        with doc.transaction():
            n = len(contributions)
            for _ in range(n):
                del contributions[0]

    # ── Cursors (stretch feature) ───────────────────────────────────────

    async def set_cursor(
        self,
        room_id: str,
        agent: AgentParticipant,
        x: float,
        y: float,
        *,
        activity: str | None = None,
    ) -> None:
        """Park an agent cursor at a position. Subsequent calls update
        the same cursor entry (no animation server-side — the frontend
        can interpolate if it wants smoothness)."""
        doc = await self._get_doc(room_id)
        cursors: Map = doc.get("agent_cursors", type=Map)
        payload = AgentCursor(
            agent_id=agent.id,
            name=agent.name,
            accent=agent.accent,
            glyph=agent.glyph,
            x=x,
            y=y,
            activity=activity,
            updated_at=time.time(),
        )
        with doc.transaction():
            cursors[agent.id] = payload.to_dict()

    async def clear_cursor(self, room_id: str, agent_id: str) -> None:
        doc = await self._get_doc(room_id)
        cursors: Map = doc.get("agent_cursors", type=Map)
        with doc.transaction():
            if agent_id in cursors:
                del cursors[agent_id]

    async def clear_all_cursors(self, room_id: str) -> None:
        doc = await self._get_doc(room_id)
        cursors: Map = doc.get("agent_cursors", type=Map)
        with doc.transaction():
            for key in list(cursors.keys()):
                del cursors[key]

    # ── Chat-panel messages (Phase 5) ───────────────────────────────────

    async def post_message(self, room_id: str, message: AgentChatMessage) -> None:
        """Append a chat-panel message — see helpers in
        :mod:`core.engine.canvas_bridge.messages` for typed constructors
        (:func:`attention_request`, :func:`agent_note`)."""
        await _post_message(self, room_id, message)

    async def clear_messages(self, room_id: str) -> None:
        """Wipe all chat messages in a room."""
        await _clear_messages(self, room_id)

    def observe_user_replies(self, room_id: str, on_reply) -> "callable":
        """Subscribe to user-reply messages in a room. Returns an
        unsubscribe callable. The callback may be sync or async; async
        callbacks are scheduled on the event loop."""
        return _observe_user_replies(self, lambda: room_id, on_reply)

    # ── Convenience: derive position for a lens ─────────────────────────

    def default_position(self, lens_or_id: str) -> dict[str, int]:
        """Default starting box for a lens — see DEFAULT_LAYOUT."""
        return DEFAULT_LAYOUT.get(lens_or_id, {"x": 0, "y": 0, "w": 280, "h": 200})


_singleton: CanvasBridge | None = None


def bridge() -> CanvasBridge:
    """Get the process-level :class:`CanvasBridge` singleton."""
    global _singleton
    if _singleton is None:
        _singleton = CanvasBridge()
    return _singleton


# Re-export for caller convenience
__all__ = [
    "AgentContribution",
    "AgentCursor",
    "AgentParticipant",
    "CanvasBridge",
    "DEFAULT_LAYOUT",
    "bridge",
    "get_participant",
]
