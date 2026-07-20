# engine/orchestration/atc_monitor.py
"""ATC Monitor — runtime airspace enforcement during agent execution.

Listens for edit.airspace_violation events on the main event bus.
When an agent modifies a file outside its assigned airspace, the monitor:
1. Logs the violation
2. Sends a warning to the agent via inject_message()
3. Records the violation for post-execution review

Violations are best-effort warnings — they don't cancel the agent.
The goal is prevention through awareness, not punishment.
"""

from __future__ import annotations

import logging
from typing import Any

from core.engine.orchestration.airspace import AirspaceAssignment
from core.engine.orchestration.bus import BusMessage, MessageType

logger = logging.getLogger(__name__)


class ATCMonitor:
    """Runtime airspace enforcement for a batch of parallel agents.

    Usage:
        monitor = ATCMonitor(assignments)
        monitor.register_agent(unit_id, shell)
        monitor.start()
        # ... agents execute ...
        monitor.stop()
        print(monitor.violations)
    """

    def __init__(self, assignments: dict[str, AirspaceAssignment]):
        self._assignments = assignments
        self._violations: list[dict] = []
        self._agents: dict[str, Any] = {}  # session_id -> AgentShell
        self._handler_ref = None

    def register_agent(self, session_id: str, shell: Any) -> None:
        """Register an agent shell so we can inject_message on violations."""
        self._agents[session_id] = shell

    def start(self) -> None:
        """Register violation handler on the main event bus."""
        from core.engine.events.bus import bus

        self._handler_ref = self._on_airspace_violation
        bus.on("edit.airspace_violation", self._handler_ref)
        logger.info("ATC monitor started for %d units", len(self._assignments))

    def stop(self) -> None:
        """Unregister handler and finalize."""
        from core.engine.events.bus import bus

        if self._handler_ref:
            bus.off("edit.airspace_violation", self._handler_ref)
            self._handler_ref = None

        if self._violations:
            logger.warning(
                "ATC monitor stopped: %d violations detected",
                len(self._violations),
            )
        else:
            logger.info("ATC monitor stopped: no violations")

    async def _on_airspace_violation(self, event_type: str, payload: dict) -> None:
        """Handle an airspace violation event.

        Logs it, records it, and sends a warning to the agent if possible.
        """
        session_id = payload.get("session_id", "")
        file_id = payload.get("file", "")

        self._violations.append(payload)
        logger.warning(
            "ATC violation: session %s modified %s (outside assigned airspace)",
            session_id,
            file_id,
        )

        # Try to warn the agent via inject_message
        shell = self._agents.get(session_id)
        if shell:
            try:
                warning = BusMessage(
                    type=MessageType.BROADCAST,
                    source_agent_id="atc_monitor",
                    target_agent_id=session_id,
                    payload={
                        "warning": (
                            f"Airspace violation: you modified {file_id} which is "
                            f"outside your assigned file set. Please stay within "
                            f"your assigned files."
                        ),
                        "action": "stay_within_assignment",
                        "file": file_id,
                    },
                )
                await shell.inject_message(warning)
            except Exception as exc:
                logger.debug("Failed to inject ATC warning: %s", exc)

    @property
    def violations(self) -> list[dict]:
        """Return all violations detected during this monitoring session."""
        return list(self._violations)
