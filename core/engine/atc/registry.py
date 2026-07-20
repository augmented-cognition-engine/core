# engine/atc/registry.py
"""Flight Registry — CRUD + lifecycle for ATC flights.

Every change set (agent task, initiative, human PR) is registered as a
flight.  The registry tracks status, capabilities, and provides the
queries that the scheduler and UI need.

Flights flow: planning → cleared → active → landing → landed
                ↓           ↓         ↓
              holding ←──────┘    cancelled/failed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.engine.core.db import parse_one, parse_rows
from core.engine.events.bus import bus
from core.engine.live.state_machines import ATCFlightMachine, InvalidTransition

logger = logging.getLogger(__name__)


@dataclass
class Flight:
    """In-memory representation of an atc_flight record."""

    id: str = ""
    product_id: str = ""
    source: str = ""  # initiative, task, human_pr, human_branch
    source_id: str = ""
    title: str = ""
    capabilities: list[str] = field(default_factory=list)
    files_predicted: list[str] = field(default_factory=list)
    files_actual: list[str] | None = None
    status: str = "planning"
    priority: int = 50
    blocked_by: str | None = None
    worktree_path: str | None = None
    target_branch: str = "main"


class FlightRegistry:
    """Manage atc_flight records in SurrealDB."""

    def __init__(self, db_pool):
        self._pool = db_pool

    async def register(
        self,
        product_id: str,
        source: str,
        source_id: str,
        title: str = "",
        capabilities: list[str] | None = None,
        files_predicted: list[str] | None = None,
        priority: int = 50,
        target_branch: str = "main",
    ) -> Flight:
        """Register a new flight in 'planning' status.

        Call this when a task enters the queue, an initiative is created,
        or a human PR is detected.
        """
        async with self._pool.connection() as db:
            result = await db.query(
                """CREATE atc_flight SET
                    source = $source,
                    source_id = $source_id,
                    title = $title,
                    capabilities = $capabilities,
                    files_predicted = $files,
                    status = 'planning',
                    priority = $priority,
                    target_branch = $target_branch,
                    plan_created_at = time::now(),
                    created_at = time::now(),
                    updated_at = time::now()""",
                {
                    "product": product_id,
                    "source": source,
                    "source_id": source_id,
                    "title": title,
                    "capabilities": capabilities or [],
                    "files": files_predicted or [],
                    "priority": priority,
                    "target_branch": target_branch,
                },
            )
            record = parse_one(result)

        flight_id = str(record["id"]) if record else ""

        await bus.emit(
            "flight.registered",
            {
                "product_id": product_id,
                "flight_id": flight_id,
                "source": source,
                "source_id": source_id,
                "capabilities": capabilities or [],
                "status": "planning",
            },
        )

        return Flight(
            id=flight_id,
            product_id=product_id,
            source=source,
            source_id=source_id,
            title=title,
            capabilities=capabilities or [],
            files_predicted=files_predicted or [],
            priority=priority,
            target_branch=target_branch,
        )

    async def transition(self, flight_id: str, target_status: str) -> Flight:
        """Transition a flight to a new status. Validates via state machine."""
        async with self._pool.connection() as db:
            result = await db.query(
                "SELECT * FROM ONLY <record>$id",
                {"id": flight_id},
            )
            record = parse_one(result)
            if not record:
                raise ValueError(f"Flight {flight_id} not found")

            current = record.get("status", "planning")
            machine = ATCFlightMachine(current)
            machine.transition(target_status)  # raises InvalidTransition if invalid

            # Build update fields
            update_parts = ["status = $status", "updated_at = time::now()"]
            params: dict = {"id": flight_id, "status": target_status}

            if target_status == "cleared":
                update_parts.append("cleared_at = time::now()")
            elif target_status == "landed":
                update_parts.append("landed_at = time::now()")
            elif target_status == "holding":
                pass  # blocked_by set separately via hold()

            update_clause = ", ".join(update_parts)
            result = await db.query(
                f"UPDATE <record>$id SET {update_clause}",
                params,
            )
            updated = parse_one(result) or record

        product_id = str(record.get("product", ""))
        await bus.emit(
            f"flight.{target_status}",
            {
                "product_id": product_id,
                "flight_id": flight_id,
                "old_status": current,
                "new_status": target_status,
                "source": record.get("source", ""),
                "capabilities": record.get("capabilities", []),
            },
        )

        return self._to_flight(updated)

    async def hold(self, flight_id: str, blocked_by: str) -> Flight:
        """Put a flight in holding pattern, blocked by another flight."""
        async with self._pool.connection() as db:
            result = await db.query(
                "SELECT * FROM ONLY <record>$id",
                {"id": flight_id},
            )
            record = parse_one(result)
            if not record:
                raise ValueError(f"Flight {flight_id} not found")

            current = record.get("status", "planning")
            machine = ATCFlightMachine(current)
            machine.transition("holding")

            result = await db.query(
                """UPDATE <record>$id SET
                    status = 'holding',
                    blocked_by = <record>$blocker,
                    updated_at = time::now()""",
                {"id": flight_id, "blocker": blocked_by},
            )
            updated = parse_one(result) or record

        product_id = str(record.get("product", ""))
        await bus.emit(
            "flight.holding",
            {
                "product_id": product_id,
                "flight_id": flight_id,
                "blocked_by": blocked_by,
                "capabilities": record.get("capabilities", []),
            },
        )

        return self._to_flight(updated)

    async def update_files_actual(self, flight_id: str, files: list[str]) -> None:
        """Record the actual files modified (post-execution)."""
        async with self._pool.connection() as db:
            await db.query(
                "UPDATE <record>$id SET files_actual = $files, updated_at = time::now()",
                {"id": flight_id, "files": files},
            )

    async def update_capabilities(self, flight_id: str, capabilities: list[str]) -> None:
        """Update capability list (e.g., after graph enrichment)."""
        async with self._pool.connection() as db:
            await db.query(
                "UPDATE <record>$id SET capabilities = $caps, updated_at = time::now()",
                {"id": flight_id, "caps": capabilities},
            )

    async def get(self, flight_id: str) -> Flight | None:
        """Get a single flight by ID."""
        async with self._pool.connection() as db:
            result = await db.query(
                "SELECT * FROM ONLY <record>$id",
                {"id": flight_id},
            )
            record = parse_one(result)
        return self._to_flight(record) if record else None

    async def get_active_flights(self, product_id: str) -> list[Flight]:
        """Get all non-terminal flights (not landed/cancelled)."""
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT * FROM atc_flight
                WHERE product = <record>$product
                  AND status NOT IN ['landed', 'cancelled']
                ORDER BY priority ASC, created_at ASC""",
                {"product": product_id},
            )
            rows = parse_rows(result)
        return [self._to_flight(r) for r in rows]

    async def get_holding_flights(self, product_id: str) -> list[Flight]:
        """Get flights in holding pattern."""
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT * FROM atc_flight
                WHERE product = <record>$product AND status = 'holding'
                ORDER BY priority ASC, created_at ASC""",
                {"product": product_id},
            )
            rows = parse_rows(result)
        return [self._to_flight(r) for r in rows]

    async def get_flights_holding_on(self, blocker_id: str, product_id: str) -> list[Flight]:
        """Get flights blocked by a specific flight (for cascade clearance)."""
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT * FROM atc_flight
                WHERE product = <record>$product
                  AND status = 'holding'
                  AND blocked_by = <record>$blocker
                ORDER BY priority ASC""",
                {"product": product_id, "blocker": blocker_id},
            )
            rows = parse_rows(result)
        return [self._to_flight(r) for r in rows]

    async def check_capability_conflicts(
        self,
        capabilities: list[str],
        product_id: str,
        exclude_flight: str | None = None,
    ) -> list[Flight]:
        """Find active flights that occupy any of the given capabilities.

        This is the core ATC query: "is anyone else in this airspace?"
        """
        if not capabilities:
            return []

        async with self._pool.connection() as db:
            # Check for flights in active states that overlap on capabilities
            result = await db.query(
                """SELECT * FROM atc_flight
                WHERE product = <record>$product
                  AND status IN ['cleared', 'active', 'landing']
                  AND capabilities CONTAINSANY $caps""",
                {"product": product_id, "caps": capabilities},
            )
            rows = parse_rows(result)

        conflicts = [self._to_flight(r) for r in rows]

        if exclude_flight:
            conflicts = [f for f in conflicts if f.id != exclude_flight]

        return conflicts

    async def clear_holding_flights(self, landed_flight_id: str, product_id: str) -> list[Flight]:
        """When a flight lands, check if any holding flights can now be cleared.

        Called after a flight transitions to 'landed'. Finds flights blocked
        by this one and transitions them to 'cleared' if their capabilities
        are now free.
        """
        waiting = await self.get_flights_holding_on(landed_flight_id, product_id)
        cleared = []

        for flight in waiting:
            # Check if their capabilities are now free
            conflicts = await self.check_capability_conflicts(
                flight.capabilities,
                product_id,
                exclude_flight=flight.id,
            )
            if not conflicts:
                try:
                    updated = await self.transition(flight.id, "cleared")
                    cleared.append(updated)
                    logger.info(
                        "Flight %s cleared (was holding on %s)",
                        flight.id,
                        landed_flight_id,
                    )
                except InvalidTransition:
                    pass

        return cleared

    def _to_flight(self, record: dict) -> Flight:
        """Convert a DB record to a Flight dataclass."""
        return Flight(
            id=str(record.get("id", "")),
            product_id=str(record.get("product", "")),
            source=record.get("source", ""),
            source_id=record.get("source_id", ""),
            title=record.get("title", ""),
            capabilities=record.get("capabilities", []),
            files_predicted=record.get("files_predicted", []),
            files_actual=record.get("files_actual"),
            status=record.get("status", "planning"),
            priority=record.get("priority", 50),
            blocked_by=str(record["blocked_by"]) if record.get("blocked_by") else None,
            worktree_path=record.get("worktree_path"),
            target_branch=record.get("target_branch", "main"),
        )
