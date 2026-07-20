"""Agent participant bridge for the ACE canvas (Phase 4 of
``docs/superpowers/specs/2026-05-26-canvas-path-c-multiplayer-board.md``).

This module is the novel ACE-specific layer on top of the Yjs sync
infrastructure: it lets backend agents act as first-class participants
on the canvas board — drop contribution notes, mark them in-flight,
land them, address the user — alongside human cursors and changes.

Public surface:

- :class:`AgentParticipant` — synthetic identity for one lens or the
  partner (id, name, accent, glyph).
- :class:`CanvasBridge` — process-level singleton that mutates the
  shared Yjs ``Doc`` for each active room. Reaches into the
  :mod:`core.engine.api.canvas_yjs` WebsocketServer to find rooms.
- :func:`bridge` — accessor for the singleton.

Architecture:

The browser-facing Y.Doc carries two collaborative surfaces beyond the
tldraw snapshot itself:

  Y.Doc
    ├─ Y.Map('board')                  # ['tldraw-snapshot'] → store snapshot
    ├─ Y.Array('agent_contributions')  # streaming agent voice writes
    └─ Y.Map('agent_cursors')          # transient cursor positions

Agents append to ``agent_contributions``. The frontend observer in
``core/ui/canvas/src/app/board/agentSubscription.ts`` materializes
each entry into a tldraw shape, so the backend never has to know
tldraw's internal record format. Updates to an existing contribution
(in-flight → landed) are written by replacing the array entry in place.
"""

from core.engine.canvas_bridge.bridge import CanvasBridge, bridge
from core.engine.canvas_bridge.participant import AgentParticipant

__all__ = ["AgentParticipant", "CanvasBridge", "bridge"]
