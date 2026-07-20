"""Chat-panel message types + bridge methods (Phase 5 of
``docs/superpowers/specs/2026-05-26-canvas-path-c-multiplayer-board.md``).

Messages live in a ``Y.Array`` on the shared Y.Doc, keyed under
``chat_messages``. The frontend ``ChatPanel`` observes this array;
the user's reply input writes ``user-reply`` entries back; bridge
methods on :class:`~core.engine.canvas_bridge.bridge.CanvasBridge`
write ``attention-request`` and ``agent-note`` entries.

Schema mirrors ``core/ui/canvas/src/app/board/messages.ts`` —
``camelCase`` field names on the wire so the JS observer can pass
values through unchanged.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from logging import getLogger
from typing import Literal

from pycrdt import Array

from core.engine.canvas_bridge.participant import AgentParticipant

logger = getLogger(__name__)

MessageType = Literal["attention-request", "user-reply", "agent-note"]


@dataclass
class AgentChatMessage:
    """Bridge-side representation of a chat-panel message.

    Field names map to the frontend ``BoardMessage`` interface in
    ``core/ui/canvas/src/app/board/messages.ts``. ``to_dict`` converts
    snake_case to camelCase where they diverge.
    """

    type: MessageType
    speaker: str
    accent: str
    glyph: str
    body: str
    id: str = field(default_factory=lambda: f"agent-{uuid.uuid4().hex[:12]}")
    posted_at: float = field(default_factory=lambda: time.time() * 1000)
    triggered_by: str | None = None
    from_agent_id: str | None = None
    from_user: bool = False
    in_reply_to_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "id": self.id,
            "type": self.type,
            "speaker": self.speaker,
            "accent": self.accent,
            "glyph": self.glyph,
            "body": self.body,
            "postedAt": self.posted_at,
        }
        if self.triggered_by is not None:
            d["triggeredBy"] = self.triggered_by
        if self.from_agent_id is not None:
            d["fromAgentId"] = self.from_agent_id
        if self.from_user:
            d["fromUser"] = True
        if self.in_reply_to_id is not None:
            d["inReplyToId"] = self.in_reply_to_id
        return d


def from_dict(d: dict[str, object]) -> AgentChatMessage:
    """Construct an AgentChatMessage from a wire dict (camelCase)."""
    return AgentChatMessage(
        id=str(d.get("id", "")),
        type=str(d.get("type", "agent-note")),  # type: ignore[arg-type]
        speaker=str(d.get("speaker", "")),
        accent=str(d.get("accent", "var(--ace-ink-muted)")),
        glyph=str(d.get("glyph", "·")),
        body=str(d.get("body", "")),
        posted_at=float(d.get("postedAt", 0.0)),  # type: ignore[arg-type]
        triggered_by=_opt_str(d.get("triggeredBy")),
        from_agent_id=_opt_str(d.get("fromAgentId")),
        from_user=bool(d.get("fromUser", False)),
        in_reply_to_id=_opt_str(d.get("inReplyToId")),
    )


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


# ── Helpers to construct typed messages from agents ──────────────────────────


def attention_request(agent: AgentParticipant, body: str, triggered_by: str | None = None) -> AgentChatMessage:
    """Build an ``attention-request`` message from an agent.

    Rendered by the chat panel via the existing ``AttentionCallout``
    component, so it gets the "Speaker → you · just now" header + inline
    ask-back input automatically.
    """
    return AgentChatMessage(
        type="attention-request",
        speaker=agent.name,
        accent=agent.accent,
        glyph=agent.glyph,
        body=body,
        triggered_by=triggered_by,
        from_agent_id=agent.id,
    )


def agent_note(agent: AgentParticipant, body: str) -> AgentChatMessage:
    """Build an ``agent-note`` (side comment, not a question)."""
    return AgentChatMessage(
        type="agent-note",
        speaker=agent.name,
        accent=agent.accent,
        glyph=agent.glyph,
        body=body,
        from_agent_id=agent.id,
    )


# ── Bridge methods (attached as mixin to CanvasBridge in bridge.py) ──────────


CHAT_MESSAGES_KEY = "chat_messages"


def _messages_array(doc) -> Array:
    return doc.get(CHAT_MESSAGES_KEY, type=Array)


async def post_message(bridge, room_id: str, message: AgentChatMessage) -> None:
    """Append a message to the room's chat-messages array."""
    doc = await bridge._get_doc(room_id)
    messages = _messages_array(doc)
    with doc.transaction():
        messages.append(message.to_dict())
    logger.info(
        "bridge: post_message room=%s type=%s speaker=%s",
        room_id,
        message.type,
        message.speaker,
    )


async def clear_messages(bridge, room_id: str) -> None:
    """Wipe all chat messages in a room — useful between demos."""
    doc = await bridge._get_doc(room_id)
    messages = _messages_array(doc)
    with doc.transaction():
        n = len(messages)
        for _ in range(n):
            del messages[0]


def observe_user_replies(
    bridge,
    room_id_resolver: Callable[[], str],
    on_reply: Callable[[AgentChatMessage], Awaitable[None] | None],
) -> Callable[[], None]:
    """Register a callback that fires whenever a user-reply is appended.

    Returns an unsubscribe function. Caller is responsible for keeping
    the room alive (e.g. running a demo).

    Uses Yjs Array's observe — fires for any structural mutation; we
    filter to ``user-reply`` entries that we haven't seen before. The
    bridge-side acknowledgement logic lives in :func:`responder` (see
    :mod:`core.engine.canvas_bridge.demo`).
    """
    import asyncio

    seen_ids: set[str] = set()

    async def _maybe_call(message: AgentChatMessage) -> None:
        result = on_reply(message)
        if asyncio.iscoroutine(result):
            await result

    async def _async_observe() -> Callable[[], None]:
        room_id = room_id_resolver()
        doc = await bridge._get_doc(room_id)
        messages = _messages_array(doc)

        def _on_change(_event) -> None:
            for entry in messages:
                if not isinstance(entry, dict):
                    continue
                msg = from_dict(entry)
                if msg.type != "user-reply":
                    continue
                if msg.id in seen_ids:
                    continue
                seen_ids.add(msg.id)
                # Use call_soon to dispatch the async handler outside of
                # the Yjs transaction observer (which is sync).
                asyncio.create_task(_maybe_call(msg))

        # Initialize seen_ids with whatever is already in the array
        # (so we don't fire on historical entries).
        for entry in messages:
            if isinstance(entry, dict):
                eid = str(entry.get("id", ""))
                if eid:
                    seen_ids.add(eid)

        messages.observe(_on_change)
        return lambda: messages.unobserve(_on_change)

    # We can't return an awaitable from a sync API; spin up the
    # observer setup as a task and return a placeholder cleanup
    # that's swapped in once subscription completes.
    cleanup: list[Callable[[], None]] = [lambda: None]

    async def _setup_and_swap() -> None:
        cleanup[0] = await _async_observe()

    asyncio.create_task(_setup_and_swap())

    def unsubscribe() -> None:
        cleanup[0]()

    return unsubscribe
