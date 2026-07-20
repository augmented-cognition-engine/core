"""SessionAdapter — protocol every tool adapter must satisfy."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.engine.session.models import SessionEvent, SessionTurn


@runtime_checkable
class SessionAdapter(Protocol):
    """Translate tool-specific raw events into the uniform Session model.

    Each supported tool (Claude Code, Cursor, Codex, …) ships its own
    adapter. The registry maps the ``source`` string on a Session to the
    correct adapter instance.
    """

    def ingest(self, raw_event: Any) -> SessionEvent:
        """Normalize one raw event into a SessionEvent.

        The returned SessionEvent MUST NOT contain tool-specific field names
        in its serialized form (the sentinel check enforces this).
        """
        ...

    def enumerate_turns(self, session_id: str) -> list[SessionTurn]:
        """Reconstruct ordered turns for an existing session.

        Returns an empty list when turn data is unavailable — never raises.
        """
        ...
