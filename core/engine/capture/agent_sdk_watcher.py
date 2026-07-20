"""AgentSDKWatcher — StreamWatcher for Claude Agent SDK streaming sessions.

Maps Agent SDK stream events to ACE's StreamEvent protocol.
Does NOT depend on claude_agent_sdk package — accepts any async iterator of dicts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from core.engine.capture.watchers import StreamEvent


class AgentSDKWatcher:
    """Watch a Claude Agent SDK streaming session.

    Accepts an async iterator of message dicts (from the Agent SDK's query()
    with include_partial_messages=True). Maps SDK events to ACE StreamEvents.
    """

    def __init__(self, sdk_stream: AsyncIterator, session_id: str) -> None:
        self.sdk_stream = sdk_stream
        self.session_id = session_id

    async def watch(self) -> AsyncIterator[StreamEvent]:
        async for message in self.sdk_stream:
            if not isinstance(message, dict):
                continue
            if message.get("type") != "stream_event":
                continue

            event = message.get("event", {})
            event_type = event.get("type")

            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                delta_type = delta.get("type")

                if delta_type == "text_delta":
                    yield StreamEvent(
                        timestamp=datetime.now(timezone.utc),
                        event_type="text",
                        content=delta.get("text", ""),
                        session_id=self.session_id,
                    )
                elif delta_type == "input_json_delta":
                    yield StreamEvent(
                        timestamp=datetime.now(timezone.utc),
                        event_type="tool_use",
                        content=delta.get("partial_json", ""),
                        session_id=self.session_id,
                    )

            elif event_type == "content_block_stop":
                yield StreamEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="status",
                    content="block_complete",
                    session_id=self.session_id,
                )

            elif event_type == "message_stop":
                yield StreamEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="status",
                    content="message_complete",
                    session_id=self.session_id,
                )
