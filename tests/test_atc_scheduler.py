# tests/test_atc_scheduler.py
"""Tests for ATC Scheduler — capability-aware task scheduling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.atc.registry import Flight

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


def _mock_registry():
    """Create a mock FlightRegistry."""
    registry = AsyncMock()
    registry.register = AsyncMock(return_value=Flight(id="atc_flight:new", status="planning"))
    registry.transition = AsyncMock(return_value=Flight(id="atc_flight:new", status="cleared"))
    registry.hold = AsyncMock(return_value=Flight(id="atc_flight:new", status="holding"))
    registry.check_capability_conflicts = AsyncMock(return_value=[])
    registry.clear_holding_flights = AsyncMock(return_value=[])
    registry.update_files_actual = AsyncMock()
    return registry


# ═══════════════════════════════════════════════════════════════════════════════
# 1. try_clear — No conflicts
# ═══════════════════════════════════════════════════════════════════════════════


class TestTryClearNoConflicts:
    """Task gets cleared when no capability conflicts exist."""

    @pytest.mark.asyncio
    async def test_cleared_when_no_conflicts(self):
        """Task with capabilities but no conflicts is cleared."""
        from core.engine.atc.scheduler import ATCScheduler

        scheduler = ATCScheduler(db_pool=_make_pool())
        scheduler._registry = _mock_registry()

        item = {"description": "Build auth", "capabilities": ["auth_system"]}
        result = await scheduler.try_clear("q:1", item, "product:test")

        assert result is True
        scheduler._registry.register.assert_called_once()
        scheduler._registry.transition.assert_called_once()  # → cleared

    @pytest.mark.asyncio
    async def test_cleared_when_no_capabilities_resolved(self):
        """Task with no resolvable capabilities bypasses ATC (let it through)."""
        from core.engine.atc.scheduler import ATCScheduler

        scheduler = ATCScheduler(db_pool=_make_pool())
        scheduler._registry = _mock_registry()

        item = {"description": "Do something vague"}
        result = await scheduler.try_clear("q:2", item, "product:test")

        assert result is True
        scheduler._registry.register.assert_not_called()  # bypassed ATC entirely


# ═══════════════════════════════════════════════════════════════════════════════
# 2. try_clear — Conflicts → holding
# ═══════════════════════════════════════════════════════════════════════════════


class TestTryClearWithConflicts:
    """Task enters holding pattern when capabilities are occupied."""

    @pytest.mark.asyncio
    async def test_blocked_enters_holding(self):
        """Task blocked by active flight enters holding pattern."""
        from core.engine.atc.scheduler import ATCScheduler

        registry = _mock_registry()
        blocker = Flight(
            id="atc_flight:blocker",
            source="initiative",
            source_id="init:xyz",
            capabilities=["auth_system"],
            status="active",
        )
        registry.check_capability_conflicts = AsyncMock(return_value=[blocker])

        scheduler = ATCScheduler(db_pool=_make_pool())
        scheduler._registry = registry

        item = {"description": "Also needs auth", "capabilities": ["auth_system"]}
        result = await scheduler.try_clear("q:blocked", item, "product:test")

        assert result is False
        registry.hold.assert_called_once()

    @pytest.mark.asyncio
    async def test_second_try_clear_reuses_flight(self):
        """Calling try_clear again for same queue_id doesn't re-register."""
        from core.engine.atc.scheduler import ATCScheduler

        registry = _mock_registry()
        # First call: no conflicts → cleared
        # Second call: conflicts appear → holding
        registry.check_capability_conflicts = AsyncMock(
            side_effect=[[], [Flight(id="atc_flight:x", capabilities=["auth"], status="active")]]
        )

        scheduler = ATCScheduler(db_pool=_make_pool())
        scheduler._registry = registry

        item = {"capabilities": ["auth"]}

        await scheduler.try_clear("q:reuse", item, "product:test")
        assert registry.register.call_count == 1

        await scheduler.try_clear("q:reuse", item, "product:test")
        # Should NOT register again — reuses existing flight
        assert registry.register.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Execution lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecutionLifecycle:
    """Test on_execution_start, on_execution_complete, on_execution_failed."""

    @pytest.mark.asyncio
    async def test_on_start_transitions_to_active(self):
        """on_execution_start transitions flight to active."""
        from core.engine.atc.scheduler import ATCScheduler

        registry = _mock_registry()
        scheduler = ATCScheduler(db_pool=_make_pool())
        scheduler._registry = registry
        scheduler._queue_to_flight["q:1"] = "atc_flight:abc"

        await scheduler.on_execution_start("q:1")

        registry.transition.assert_called_with("atc_flight:abc", "active")

    @pytest.mark.asyncio
    async def test_on_complete_lands_and_cascades(self):
        """on_execution_complete: active → landing → landed, then clears holding."""
        from core.engine.atc.scheduler import ATCScheduler

        registry = _mock_registry()
        registry.clear_holding_flights = AsyncMock(
            return_value=[
                Flight(id="atc_flight:waiting", status="cleared"),
            ]
        )

        scheduler = ATCScheduler(db_pool=_make_pool())
        scheduler._registry = registry
        scheduler._queue_to_flight["q:1"] = "atc_flight:done"

        await scheduler.on_execution_complete("q:1", "product:test", files_actual=["auth.py"])

        # Should transition: landing then landed
        calls = [c[0] for c in registry.transition.call_args_list]
        assert ("atc_flight:done", "landing") in calls
        assert ("atc_flight:done", "landed") in calls

        # Should update files_actual
        registry.update_files_actual.assert_called_once_with("atc_flight:done", ["auth.py"])

        # Should cascade clear
        registry.clear_holding_flights.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_failed_transitions_and_cascades(self):
        """on_execution_failed: → failed, still cascades holding flights."""
        from core.engine.atc.scheduler import ATCScheduler

        registry = _mock_registry()
        scheduler = ATCScheduler(db_pool=_make_pool())
        scheduler._registry = registry
        scheduler._queue_to_flight["q:1"] = "atc_flight:fail"

        await scheduler.on_execution_failed("q:1", "product:test")

        registry.transition.assert_called_with("atc_flight:fail", "failed")
        registry.clear_holding_flights.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_flight_id_is_noop(self):
        """Calling lifecycle methods with unknown queue_id is a no-op."""
        from core.engine.atc.scheduler import ATCScheduler

        registry = _mock_registry()
        scheduler = ATCScheduler(db_pool=_make_pool())
        scheduler._registry = registry

        await scheduler.on_execution_start("q:unknown")
        await scheduler.on_execution_complete("q:unknown", "product:test")
        await scheduler.on_execution_failed("q:unknown", "product:test")

        registry.transition.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Capability Resolution
# ═══════════════════════════════════════════════════════════════════════════════


class TestCapabilityResolution:
    """Test _resolve_capabilities fallback chain."""

    @pytest.mark.asyncio
    async def test_explicit_capabilities(self):
        """Capabilities on the item are used directly."""
        from core.engine.atc.scheduler import ATCScheduler

        scheduler = ATCScheduler(db_pool=_make_pool())

        item = {"capabilities": ["auth_system", "billing"]}
        caps = await scheduler._resolve_capabilities(item, "product:test")

        assert caps == ["auth_system", "billing"]

    @pytest.mark.asyncio
    async def test_from_work_item(self):
        """Capabilities loaded from work_item record."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"capabilities": ["data_modeling"]}]])

        from core.engine.atc.scheduler import ATCScheduler

        scheduler = ATCScheduler(db_pool=_make_pool(db))

        item = {"work_item_id": "work_item:abc"}
        caps = await scheduler._resolve_capabilities(item, "product:test")

        assert caps == ["data_modeling"]

    @pytest.mark.asyncio
    async def test_empty_when_nothing_resolves(self):
        """Returns empty list when no capabilities can be resolved."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        from core.engine.atc.scheduler import ATCScheduler

        scheduler = ATCScheduler(db_pool=_make_pool(db))

        item = {"description": "do something with no file references"}
        caps = await scheduler._resolve_capabilities(item, "product:test")

        assert caps == []


# ═══════════════════════════════════════════════════════════════════════════════
# 5. TaskRunner ATC Integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestTaskRunnerATCIntegration:
    """Test that TaskRunner initializes and uses the ATC scheduler."""

    @pytest.mark.asyncio
    async def test_runner_initializes_scheduler(self):
        """TaskRunner.start() creates an ATCScheduler."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])

        from core.engine.runner.daemon import TaskRunner

        runner = TaskRunner(db_pool=_make_pool(db), default_org="product:test")
        await runner.start()

        assert runner._scheduler is not None
        await runner.stop()

    @pytest.mark.asyncio
    async def test_execute_item_calls_scheduler_lifecycle(self):
        """_execute_item calls on_execution_start and on_execution_complete."""
        from core.engine.orchestration.executor import OrchestrationResult

        mock_result = OrchestrationResult(
            task_id="task:1",
            output="done",
            classification={"domain_path": "testing"},
            snapshot={},
            status="completed",
        )

        db = AsyncMock()
        db.query = AsyncMock(return_value=[])

        class MockSessionRunner:
            def __init__(self, **kwargs):
                pass

            async def run(self, queue_item, product_id):
                return mock_result

        mock_scheduler = AsyncMock()
        mock_scheduler.on_execution_start = AsyncMock()
        mock_scheduler.on_execution_complete = AsyncMock()

        from core.engine.runner.daemon import TaskRunner

        runner = TaskRunner(db_pool=_make_pool(db), default_org="product:test")
        runner._scheduler = mock_scheduler

        with patch("core.engine.live.session_runner.SessionRunner", MockSessionRunner):
            await runner._execute_item(
                "task_queue:test",
                {"id": "task_queue:test", "description": "Build it", "product": "product:test"},
            )

        mock_scheduler.on_execution_start.assert_called_once()
        mock_scheduler.on_execution_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_item_calls_on_failed(self):
        """_execute_item calls on_execution_failed when task crashes."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])

        class FailingRunner:
            def __init__(self, **kwargs):
                pass

            async def run(self, queue_item, product_id):
                raise RuntimeError("boom")

        mock_scheduler = AsyncMock()
        mock_scheduler.on_execution_start = AsyncMock()
        mock_scheduler.on_execution_failed = AsyncMock()

        from core.engine.runner.daemon import TaskRunner

        runner = TaskRunner(db_pool=_make_pool(db), default_org="product:test")
        runner._scheduler = mock_scheduler

        with patch("core.engine.live.session_runner.SessionRunner", FailingRunner):
            await runner._execute_item(
                "task_queue:fail",
                {"id": "task_queue:fail", "description": "Will fail", "product": "product:test"},
            )

        mock_scheduler.on_execution_start.assert_called_once()
        mock_scheduler.on_execution_failed.assert_called_once()
