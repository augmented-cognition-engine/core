# tests/test_atc_registry.py
"""Tests for ATC Flight Registry — lifecycle, conflicts, cascade clearance."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.atc.registry import Flight, FlightRegistry
from core.engine.live.state_machines import ATCFlightMachine, InvalidTransition

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_pool(db=None):
    if db is None:
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Flight State Machine
# ═══════════════════════════════════════════════════════════════════════════════


class TestATCFlightStateMachine:
    """Test flight lifecycle transitions."""

    def test_happy_path(self):
        """planning → cleared → active → landing → landed."""
        m = ATCFlightMachine("planning")
        m.transition("cleared")
        m.transition("active")
        m.transition("landing")
        m.transition("landed")
        assert m.state == "landed"

    def test_holding_pattern(self):
        """planning → holding → cleared → active."""
        m = ATCFlightMachine("planning")
        m.transition("holding")
        m.transition("cleared")
        m.transition("active")
        assert m.state == "active"

    def test_holding_from_cleared(self):
        """cleared → holding (capability became occupied after clearance)."""
        m = ATCFlightMachine("cleared")
        m.transition("holding")
        assert m.state == "holding"

    def test_cancel_from_any_pre_landing(self):
        """Can cancel from planning, cleared, active, holding."""
        for state in ["planning", "cleared", "active", "holding"]:
            m = ATCFlightMachine(state)
            m.transition("cancelled")
            assert m.state == "cancelled"

    def test_cannot_cancel_after_landing(self):
        """Can't cancel once landing has started."""
        m = ATCFlightMachine("planning")
        m.transition("cleared")
        m.transition("active")
        m.transition("landing")
        with pytest.raises(InvalidTransition):
            m.transition("cancelled")

    def test_failed_can_retry(self):
        """failed → planning (retry the flight)."""
        m = ATCFlightMachine("active")
        m.transition("failed")
        m.transition("planning")
        assert m.state == "planning"

    def test_landed_is_terminal(self):
        """landed has no transitions."""
        m = ATCFlightMachine("planning")
        m.transition("cleared")
        m.transition("active")
        m.transition("landing")
        m.transition("landed")
        assert not m.can_transition("planning")
        assert not m.can_transition("active")

    def test_invalid_skip(self):
        """Can't skip from planning to active."""
        m = ATCFlightMachine("planning")
        with pytest.raises(InvalidTransition):
            m.transition("active")

    def test_invalid_skip_to_landed(self):
        """Can't jump from active to landed (must go through landing)."""
        m = ATCFlightMachine("active")
        with pytest.raises(InvalidTransition):
            m.transition("landed")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Flight Registry — Registration
# ═══════════════════════════════════════════════════════════════════════════════


class TestFlightRegistration:
    """Test registering flights."""

    @pytest.mark.asyncio
    async def test_register_creates_flight(self):
        """register() creates atc_flight record and emits event."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "atc_flight:abc",
                        "status": "planning",
                        "product": "product:test",
                    }
                ]
            ]
        )

        with patch("core.engine.atc.registry.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            registry = FlightRegistry(db_pool=_make_pool(db))
            flight = await registry.register(
                product_id="product:test",
                source="initiative",
                source_id="initiative:xyz",
                title="Build auth system",
                capabilities=["auth_system", "api_gateway"],
                files_predicted=["engine/auth.py", "engine/api/auth.py"],
                priority=10,
            )

        assert flight.source == "initiative"
        assert flight.capabilities == ["auth_system", "api_gateway"]
        assert flight.status == "planning"
        assert flight.priority == 10

        mock_bus.emit.assert_called_once()
        event_type = mock_bus.emit.call_args[0][0]
        assert event_type == "flight.registered"

    @pytest.mark.asyncio
    async def test_register_human_pr(self):
        """Human PRs are registered as flights too."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "atc_flight:pr42",
                        "status": "planning",
                        "product": "product:test",
                    }
                ]
            ]
        )

        with patch("core.engine.atc.registry.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            registry = FlightRegistry(db_pool=_make_pool(db))
            flight = await registry.register(
                product_id="product:test",
                source="human_pr",
                source_id="PR #42",
                title="Fix login bug",
                capabilities=["auth_system"],
            )

        assert flight.source == "human_pr"
        assert flight.source_id == "PR #42"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Flight Registry — Transitions
# ═══════════════════════════════════════════════════════════════════════════════


class TestFlightTransitions:
    """Test flight status transitions."""

    @pytest.mark.asyncio
    async def test_transition_happy_path(self):
        """planning → cleared emits flight.cleared event."""
        call_count = 0

        async def mock_query(query, params=None):
            nonlocal call_count
            call_count += 1
            if "SELECT" in query:
                return [
                    [
                        {
                            "id": "atc_flight:abc",
                            "status": "planning",
                            "product": "product:test",
                            "capabilities": ["auth"],
                        }
                    ]
                ]
            return [[{"id": "atc_flight:abc", "status": "cleared"}]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=mock_query)

        with patch("core.engine.atc.registry.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            registry = FlightRegistry(db_pool=_make_pool(db))
            flight = await registry.transition("atc_flight:abc", "cleared")

        assert flight.status == "cleared"
        mock_bus.emit.assert_called_once()
        assert mock_bus.emit.call_args[0][0] == "flight.cleared"

    @pytest.mark.asyncio
    async def test_transition_invalid_raises(self):
        """Invalid transition raises InvalidTransition."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "atc_flight:abc",
                        "status": "planning",
                        "product": "product:test",
                    }
                ]
            ]
        )

        with patch("core.engine.atc.registry.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            registry = FlightRegistry(db_pool=_make_pool(db))
            with pytest.raises(InvalidTransition):
                await registry.transition("atc_flight:abc", "landed")

    @pytest.mark.asyncio
    async def test_transition_not_found_raises(self):
        """Transitioning a non-existent flight raises ValueError."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        registry = FlightRegistry(db_pool=_make_pool(db))
        with pytest.raises(ValueError, match="not found"):
            await registry.transition("atc_flight:missing", "cleared")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Flight Registry — Hold
# ═══════════════════════════════════════════════════════════════════════════════


class TestFlightHold:
    """Test holding pattern."""

    @pytest.mark.asyncio
    async def test_hold_sets_blocked_by(self):
        """hold() transitions to holding and records blocker."""

        async def mock_query(query, params=None):
            if "SELECT" in query:
                return [[{"id": "atc_flight:b", "status": "planning", "product": "product:test", "capabilities": []}]]
            return [[{"id": "atc_flight:b", "status": "holding", "blocked_by": "atc_flight:a"}]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=mock_query)

        with patch("core.engine.atc.registry.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            registry = FlightRegistry(db_pool=_make_pool(db))
            flight = await registry.hold("atc_flight:b", blocked_by="atc_flight:a")

        assert flight.status == "holding"
        assert flight.blocked_by == "atc_flight:a"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Flight Registry — Capability Conflicts
# ═══════════════════════════════════════════════════════════════════════════════


class TestCapabilityConflicts:
    """Test the core ATC query: is anyone in this airspace?"""

    @pytest.mark.asyncio
    async def test_no_conflicts(self):
        """Empty airspace returns no conflicts."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        registry = FlightRegistry(db_pool=_make_pool(db))
        conflicts = await registry.check_capability_conflicts(
            capabilities=["billing"],
            product_id="product:test",
        )

        assert conflicts == []

    @pytest.mark.asyncio
    async def test_finds_conflicts(self):
        """Active flight occupying same capability is returned as conflict."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "atc_flight:blocker",
                        "status": "active",
                        "source": "initiative",
                        "source_id": "initiative:xyz",
                        "capabilities": ["auth_system"],
                        "product": "product:test",
                    }
                ]
            ]
        )

        registry = FlightRegistry(db_pool=_make_pool(db))
        conflicts = await registry.check_capability_conflicts(
            capabilities=["auth_system"],
            product_id="product:test",
        )

        assert len(conflicts) == 1
        assert conflicts[0].source_id == "initiative:xyz"

    @pytest.mark.asyncio
    async def test_exclude_self(self):
        """exclude_flight filters out the requesting flight."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "atc_flight:self",
                        "status": "active",
                        "capabilities": ["auth_system"],
                        "product": "product:test",
                    }
                ]
            ]
        )

        registry = FlightRegistry(db_pool=_make_pool(db))
        conflicts = await registry.check_capability_conflicts(
            capabilities=["auth_system"],
            product_id="product:test",
            exclude_flight="atc_flight:self",
        )

        assert conflicts == []

    @pytest.mark.asyncio
    async def test_empty_capabilities_no_query(self):
        """Empty capability list returns empty without querying DB."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        registry = FlightRegistry(db_pool=_make_pool(db))
        conflicts = await registry.check_capability_conflicts([], "product:test")

        assert conflicts == []
        db.query.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Flight Registry — Cascade Clearance
# ═══════════════════════════════════════════════════════════════════════════════


class TestCascadeClearance:
    """Test clearing holding flights when a blocker lands."""

    @pytest.mark.asyncio
    async def test_holding_flight_cleared_when_blocker_lands(self):
        """When flight A lands, flight B (holding on A) gets cleared."""
        call_count = 0

        async def mock_query(query, params=None):
            nonlocal call_count
            call_count += 1

            # get_flights_holding_on query
            if "blocked_by" in query and "holding" in query:
                return [
                    [
                        {
                            "id": "atc_flight:b",
                            "status": "holding",
                            "capabilities": ["auth_system"],
                            "product": "product:test",
                            "blocked_by": "atc_flight:a",
                        }
                    ]
                ]

            # check_capability_conflicts query (is auth_system free now?)
            if "CONTAINSANY" in query:
                return [[]]  # no conflicts — airspace is clear

            # transition SELECT
            if "SELECT" in query and "ONLY" in query:
                return [
                    [
                        {
                            "id": "atc_flight:b",
                            "status": "holding",
                            "product": "product:test",
                            "capabilities": ["auth_system"],
                        }
                    ]
                ]

            # transition UPDATE
            if "UPDATE" in query:
                return [
                    [
                        {
                            "id": "atc_flight:b",
                            "status": "cleared",
                        }
                    ]
                ]

            return [[]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=mock_query)

        with patch("core.engine.atc.registry.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            registry = FlightRegistry(db_pool=_make_pool(db))
            cleared = await registry.clear_holding_flights("atc_flight:a", "product:test")

        assert len(cleared) == 1
        assert cleared[0].id == "atc_flight:b"

    @pytest.mark.asyncio
    async def test_holding_flight_stays_if_other_blocker(self):
        """Flight B stays holding if another flight still occupies its capability."""

        async def mock_query(query, params=None):
            if "blocked_by" in query:
                return [
                    [
                        {
                            "id": "atc_flight:b",
                            "status": "holding",
                            "capabilities": ["auth_system"],
                            "product": "product:test",
                        }
                    ]
                ]

            if "CONTAINSANY" in query:
                # Another flight C still occupies auth_system
                return [
                    [
                        {
                            "id": "atc_flight:c",
                            "status": "active",
                            "capabilities": ["auth_system"],
                            "product": "product:test",
                        }
                    ]
                ]

            return [[]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=mock_query)

        with patch("core.engine.atc.registry.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            registry = FlightRegistry(db_pool=_make_pool(db))
            cleared = await registry.clear_holding_flights("atc_flight:a", "product:test")

        assert len(cleared) == 0  # B stays holding

    @pytest.mark.asyncio
    async def test_no_holding_flights(self):
        """No holding flights → nothing to clear."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        with patch("core.engine.atc.registry.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            registry = FlightRegistry(db_pool=_make_pool(db))
            cleared = await registry.clear_holding_flights("atc_flight:a", "product:test")

        assert cleared == []


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Flight Dataclass
# ═══════════════════════════════════════════════════════════════════════════════


class TestFlightDataclass:
    """Test Flight dataclass defaults and behavior."""

    def test_defaults(self):
        f = Flight()
        assert f.status == "planning"
        assert f.priority == 50
        assert f.capabilities == []
        assert f.target_branch == "main"
        assert f.blocked_by is None

    def test_with_values(self):
        f = Flight(
            id="atc_flight:1",
            source="human_pr",
            source_id="PR #5",
            capabilities=["auth", "billing"],
            priority=10,
        )
        assert f.source == "human_pr"
        assert len(f.capabilities) == 2
