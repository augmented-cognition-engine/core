# tests/test_e2e_orchestration_pipeline.py
"""Tests for the outer orchestration pipeline layers.

Covers what test_e2e_orchestration_scenarios.py and _wiring.py don't:
- PMDecomposer + SmartDecomposer (initiative → milestones → work units)
- TaskRunner daemon (queue polling, concurrency, dependency gating)
- Live layer (coordinator, edit tracker, state machines)
- Full e2e with SurrealDB (initiative lifecycle through DB)

Tests marked @pytest.mark.e2e require live SurrealDB.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.live.state_machines import (
    ActiveEditMachine,
    AgentSessionMachine,
    InvalidTransition,
    ResourceLockMachine,
)

pytestmark_e2e = pytest.mark.e2e


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


class MockLLM:
    """Mock LLM that returns pre-set JSON responses."""

    def __init__(self, json_response: dict | list):
        self._response = json_response
        self.calls: list[str] = []

    async def complete_json(self, prompt: str, **kwargs) -> dict | list:
        self.calls.append(prompt)
        return self._response

    async def complete(self, prompt: str, **kwargs) -> str:
        self.calls.append(prompt)
        return str(self._response)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PM DECOMPOSER
# ═══════════════════════════════════════════════════════════════════════════════


class TestPMDecomposer:
    """Test LLM-powered initiative → milestones → work items decomposition."""

    @pytest.mark.asyncio
    async def test_decompose_initiative_returns_milestones(self):
        """decompose_initiative returns 3-6 milestones with required fields."""
        llm = MockLLM(
            {
                "milestones": [
                    {
                        "title": "M1: Design schema",
                        "description": "Design DB schema",
                        "done_criteria": ["Schema documented"],
                    },
                    {
                        "title": "M2: Build API",
                        "description": "Implement REST endpoints",
                        "done_criteria": ["Endpoints pass tests"],
                    },
                    {"title": "M3: Deploy", "description": "Deploy to staging", "done_criteria": ["Staging works"]},
                ]
            }
        )

        from core.engine.pm.decompose import PMDecomposer

        decomposer = PMDecomposer(db_pool=_make_pool(), llm=llm)

        milestones = await decomposer.decompose_initiative(
            title="Build user auth",
            description="JWT-based authentication system",
            product_id="product:test",
            domain_path="architecture",
        )

        assert len(milestones) == 3
        assert milestones[0]["sequence"] == 1
        assert milestones[1]["sequence"] == 2
        assert milestones[2]["sequence"] == 3
        assert all("title" in m for m in milestones)
        assert all("done_criteria" in m for m in milestones)

    @pytest.mark.asyncio
    async def test_decompose_initiative_caps_at_max(self):
        """More than MAX_MILESTONES are truncated."""
        llm = MockLLM({"milestones": [{"title": f"M{i}", "description": f"Step {i}"} for i in range(10)]})

        from core.engine.pm.decompose import MAX_MILESTONES, PMDecomposer

        decomposer = PMDecomposer(db_pool=_make_pool(), llm=llm)

        milestones = await decomposer.decompose_initiative(
            title="Huge project",
            description="Too many milestones",
            product_id="product:test",
            domain_path="architecture",
        )

        assert len(milestones) <= MAX_MILESTONES

    @pytest.mark.asyncio
    async def test_decompose_milestone_returns_work_items(self):
        """decompose_milestone returns work items with valid archetypes/modes."""
        llm = MockLLM(
            {
                "work_items": [
                    {
                        "title": "Create models",
                        "description": "Build SQLAlchemy models",
                        "archetype": "creator",
                        "mode": "deliberative",
                        "parallel_group": 1,
                        "files_touched": ["models/user.py"],
                    },
                    {
                        "title": "Write tests",
                        "description": "Unit tests for models",
                        "archetype": "sentinel",
                        "mode": "procedural",
                        "parallel_group": 1,
                        "files_touched": ["tests/test_models.py"],
                    },
                ]
            }
        )

        from core.engine.pm.decompose import PMDecomposer

        decomposer = PMDecomposer(db_pool=_make_pool(), llm=llm)

        work_items = await decomposer.decompose_milestone(
            milestone_title="M1: Build models",
            milestone_description="Create data models",
            done_criteria=["Models pass tests"],
            initiative_title="Build auth",
            product_id="product:test",
            domain_path="data_modeling",
        )

        assert len(work_items) == 2
        assert work_items[0]["archetype"] == "creator"
        assert work_items[1]["archetype"] == "sentinel"
        assert all(wi.get("parallel_group") for wi in work_items)

    @pytest.mark.asyncio
    async def test_decompose_milestone_fixes_invalid_archetypes(self):
        """Invalid archetypes/modes are corrected to defaults."""
        llm = MockLLM(
            {
                "work_items": [
                    {"title": "Bad archetype", "archetype": "wizard", "mode": "turbo"},
                ]
            }
        )

        from core.engine.pm.decompose import PMDecomposer

        decomposer = PMDecomposer(db_pool=_make_pool(), llm=llm)

        work_items = await decomposer.decompose_milestone(
            milestone_title="M1",
            milestone_description="Test",
            done_criteria=[],
            initiative_title="Test",
            product_id="product:test",
            domain_path="testing",
        )

        assert work_items[0]["archetype"] == "executor"  # default fallback
        assert work_items[0]["mode"] == "reactive"  # default fallback

    @pytest.mark.asyncio
    async def test_intelligence_context_loaded(self):
        """_load_intelligence_context queries insights for the discipline."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {"content": "Use bcrypt for passwords", "confidence": 0.9, "insight_type": "pattern"},
                ]
            ]
        )

        from core.engine.pm.decompose import PMDecomposer

        decomposer = PMDecomposer(db_pool=_make_pool(db), llm=MockLLM({"milestones": []}))

        context = await decomposer._load_intelligence_context("product:test", "security")
        assert "bcrypt" in context

    @pytest.mark.asyncio
    async def test_intelligence_context_graceful_on_failure(self):
        """_load_intelligence_context returns fallback on DB error."""
        db = AsyncMock()
        db.query = AsyncMock(side_effect=Exception("DB down"))

        from core.engine.pm.decompose import PMDecomposer

        decomposer = PMDecomposer(db_pool=_make_pool(db), llm=MockLLM({"milestones": []}))

        context = await decomposer._load_intelligence_context("product:test", "security")
        assert "no intelligence" in context.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SMART DECOMPOSER
# ═══════════════════════════════════════════════════════════════════════════════


class TestSmartDecomposer:
    """Test spec → work units → dispatch schedule pipeline."""

    @pytest.mark.asyncio
    async def test_decompose_produces_plan_with_schedule(self):
        """decompose() loads spec, LLM decomposes, runs dispatch_planner."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "agent_spec:test",
                        "objective": "Build REST API",
                        "acceptance_criteria": [{"criterion": "CRUD endpoints work"}],
                        "estimated_files": ["api.py", "models.py"],
                        "constraints": ["Use FastAPI"],
                    }
                ]
            ]
        )

        mock_llm = MockLLM(
            [
                {
                    "id": "unit-1",
                    "title": "Build models",
                    "description": "Create models",
                    "files_create": ["models.py"],
                    "files_modify": [],
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                },
                {
                    "id": "unit-2",
                    "title": "Build API",
                    "description": "Create endpoints",
                    "files_create": ["api.py"],
                    "files_modify": [],
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                },
                {
                    "id": "unit-3",
                    "title": "Write tests",
                    "description": "Test all",
                    "files_create": ["tests.py"],
                    "files_modify": [],
                    "depends_on": ["unit-1", "unit-2"],
                    "archetype": "sentinel",
                    "mode": "procedural",
                },
            ]
        )

        with patch("core.engine.product.smart_decompose.get_llm", return_value=mock_llm):
            from core.engine.product.smart_decompose import SmartDecomposer

            decomposer = SmartDecomposer(db_pool=_make_pool(db))
            decomposer._llm = mock_llm

            plan = await decomposer.decompose("agent_spec:test", "product:test")

        plan_dict = plan.to_dict()
        assert plan_dict["total_units"] == 3
        assert len(plan_dict["batches"]) >= 2  # parallel batch + sequential batch

        # unit-1 and unit-2 should be in parallel (no file overlap, no deps)
        first_batch = plan_dict["batches"][0]
        assert set(first_batch["task_ids"]) == {"unit-1", "unit-2"}
        assert first_batch["mode"] == "parallel"

    @pytest.mark.asyncio
    async def test_decompose_spec_not_found(self):
        """decompose() raises an error for missing spec."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        with patch("core.engine.product.smart_decompose.get_llm", return_value=MockLLM([])):
            from core.engine.core.exceptions import DecompositionError
            from core.engine.product.smart_decompose import SmartDecomposer

            decomposer = SmartDecomposer(db_pool=_make_pool(db))

            with pytest.raises((ValueError, DecompositionError), match="not found"):
                await decomposer.decompose("agent_spec:missing", "product:test")

    @pytest.mark.asyncio
    async def test_decompose_validates_archetypes(self):
        """Invalid archetypes from LLM are corrected to 'creator'."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "agent_spec:test",
                        "objective": "Test",
                        "acceptance_criteria": [],
                    }
                ]
            ]
        )

        mock_llm = MockLLM(
            [
                {
                    "id": "unit-1",
                    "title": "Bad",
                    "description": "X",
                    "archetype": "wizard_of_oz",
                    "mode": "ludicrous_speed",
                    "files_create": [],
                    "files_modify": [],
                    "depends_on": [],
                }
            ]
        )

        with patch("core.engine.product.smart_decompose.get_llm", return_value=mock_llm):
            from core.engine.product.smart_decompose import SmartDecomposer

            decomposer = SmartDecomposer(db_pool=_make_pool(db))
            decomposer._llm = mock_llm

            plan = await decomposer.decompose("agent_spec:test", "product:test")

        assert plan.units[0].archetype == "creator"
        assert plan.units[0].mode == "deliberative"

    @pytest.mark.asyncio
    async def test_replan_re_runs_decompose(self):
        """replan() currently just re-runs decompose (stub behavior)."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "agent_spec:test",
                        "objective": "Replan test",
                        "acceptance_criteria": [],
                    }
                ]
            ]
        )

        mock_llm = MockLLM(
            [
                {
                    "id": "unit-1",
                    "title": "Replanned",
                    "description": "After feedback",
                    "files_create": [],
                    "files_modify": [],
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                }
            ]
        )

        with patch("core.engine.product.smart_decompose.get_llm", return_value=mock_llm):
            from core.engine.product.smart_decompose import SmartDecomposer

            decomposer = SmartDecomposer(db_pool=_make_pool(db))
            decomposer._llm = mock_llm

            plan = await decomposer.replan("agent_spec:test", {"type": "blocker"}, "product:test")

        assert len(plan.units) == 1
        assert plan.units[0].title == "Replanned"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. TASK RUNNER DAEMON
# ═══════════════════════════════════════════════════════════════════════════════


class TestTaskRunnerDaemon:
    """Test queue polling, concurrency, dependency gating, pause/stop."""

    @pytest.mark.asyncio
    async def test_start_initializes_config(self):
        """start() creates runner_config and marks interrupted tasks as failed."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])

        from core.engine.runner.daemon import TaskRunner

        runner = TaskRunner(db_pool=_make_pool(db), default_org="product:test")
        await runner.start()

        # Should have queried for existing config, created it, and marked interrupted
        assert db.query.call_count >= 2
        queries = [call[0][0] for call in db.query.call_args_list]
        assert any("runner_config" in q for q in queries)
        assert any("Interrupted" in q for q in queries)

        await runner.stop()

    @pytest.mark.asyncio
    async def test_stop_waits_for_active_tasks(self):
        """stop() waits for active tasks to complete before setting status to stopped."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])

        from core.engine.runner.daemon import TaskRunner

        runner = TaskRunner(db_pool=_make_pool(db), default_org="product:test")

        # Simulate an active task
        async def slow_task():
            await asyncio.sleep(0.05)

        runner._running = True
        runner._active["q:1"] = asyncio.create_task(slow_task())

        await runner.stop()

        # Should have updated config to 'stopped'
        queries = [call[0][0] for call in db.query.call_args_list]
        assert any("stopped" in q for q in queries)
        assert len(runner._active) == 1  # task still in dict (done but not cleaned)

    @pytest.mark.asyncio
    async def test_execute_item_calls_session_runner(self):
        """_execute_item creates SessionRunner and calls run()."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])

        from core.engine.orchestration.executor import OrchestrationResult

        mock_result = OrchestrationResult(
            task_id="task:123",
            output="Task completed",
            classification={"domain_path": "testing"},
            snapshot={},
            status="completed",
        )

        session_calls: list[dict] = []

        class MockSessionRunner:
            def __init__(self, **kwargs):
                pass

            async def run(self, queue_item, product_id):
                session_calls.append({"item": queue_item, "product": product_id})
                return mock_result

        from core.engine.runner.daemon import TaskRunner

        runner = TaskRunner(db_pool=_make_pool(db), default_org="product:test")

        with patch("core.engine.live.session_runner.SessionRunner", MockSessionRunner):
            await runner._execute_item(
                "task_queue:abc",
                {"id": "task_queue:abc", "description": "Build auth", "product": "product:test"},
            )

        assert len(session_calls) == 1
        assert session_calls[0]["item"]["description"] == "Build auth"

        # Should have updated status to 'completed'
        queries = [call[0][0] for call in db.query.call_args_list]
        assert any("completed" in q for q in queries)

    @pytest.mark.asyncio
    async def test_execute_item_handles_failure(self):
        """_execute_item marks task as failed when SessionRunner raises."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])

        class FailingRunner:
            def __init__(self, **kwargs):
                pass

            async def run(self, queue_item, product_id):
                raise RuntimeError("Agent crashed")

        from core.engine.runner.daemon import TaskRunner

        runner = TaskRunner(db_pool=_make_pool(db), default_org="product:test")

        with patch("core.engine.live.session_runner.SessionRunner", FailingRunner):
            await runner._execute_item(
                "task_queue:fail",
                {"id": "task_queue:fail", "description": "Will fail", "product": "product:test"},
            )

        queries = [call[0][0] for call in db.query.call_args_list]
        assert any("failed" in q for q in queries)

    @pytest.mark.asyncio
    async def test_get_status_returns_counts(self):
        """get_status() returns running state, active/queued/completed counts."""
        call_count = 0

        async def multi_response(query, params=None):
            nonlocal call_count
            call_count += 1
            if "runner_config" in query:
                return [{"max_concurrent": 3, "mode": "all", "status": "running"}]
            elif "status = 'running'" in query:
                return [[{"id": "q:1", "description": "Active task"}]]
            elif "status = 'queued'" in query:
                return [{"count": 5}]
            elif "status = 'completed'" in query:
                return [{"count": 12}]
            return []

        db = AsyncMock()
        db.query = AsyncMock(side_effect=multi_response)

        from core.engine.runner.daemon import TaskRunner

        runner = TaskRunner(db_pool=_make_pool(db), default_org="product:test")
        runner._running = True

        status = await runner.get_status()

        assert status["running"] is True
        assert status["config"]["max_concurrent"] == 3
        assert status["queued_count"] == 5
        assert status["completed_today"] == 12


# ═══════════════════════════════════════════════════════════════════════════════
# 4. STATE MACHINES
# ═══════════════════════════════════════════════════════════════════════════════


class TestStateMachines:
    """Test state transition validation for all LIVE layer entities."""

    # --- Agent Session ---

    def test_agent_session_valid_transitions(self):
        """Valid agent session transitions succeed."""
        m = AgentSessionMachine("starting")
        assert m.transition("active") == "active"
        assert m.transition("completing") == "completing"
        assert m.transition("done") == "done"

    def test_agent_session_invalid_transition(self):
        """Invalid agent session transition raises InvalidTransition."""
        m = AgentSessionMachine("starting")
        with pytest.raises(InvalidTransition):
            m.transition("done")  # can't skip active/completing

    def test_agent_session_terminal_states(self):
        """Terminal states (done, failed, abandoned) have no transitions."""
        for state in ["done", "failed", "abandoned"]:
            m = AgentSessionMachine("starting")
            if state == "abandoned":
                m.transition("abandoned")
            elif state == "done":
                m.transition("active")
                m.transition("completing")
                m.transition("done")
            elif state == "failed":
                m.transition("active")
                m.transition("completing")
                m.transition("failed")

            assert not m.can_transition("active")
            assert not m.can_transition("starting")

    def test_agent_session_blocked_recovery(self):
        """blocked → active recovery path works."""
        m = AgentSessionMachine("active")
        m.transition("blocked")
        assert m.state == "blocked"
        m.transition("active")  # recover from blocked
        assert m.state == "active"

    def test_agent_session_abandon_from_any_active(self):
        """Any non-terminal state can transition to abandoned."""
        for state in ["starting", "active", "blocked", "completing"]:
            m = AgentSessionMachine(state)
            m.transition("abandoned")
            assert m.state == "abandoned"

    # --- Active Edit ---

    def test_active_edit_happy_path(self):
        """claimed → editing → committing → released."""
        m = ActiveEditMachine("claimed")
        m.transition("editing")
        m.transition("committing")
        m.transition("released")
        assert m.state == "released"

    def test_active_edit_conflict_resolution(self):
        """editing → conflict → resolved → released."""
        m = ActiveEditMachine("editing")
        m.transition("conflict")
        m.transition("resolved")
        m.transition("released")

    def test_active_edit_invalid_skip(self):
        """Can't skip from claimed to released."""
        m = ActiveEditMachine("claimed")
        with pytest.raises(InvalidTransition):
            m.transition("released")

    # --- Resource Lock ---

    def test_resource_lock_happy_path(self):
        """acquired → held → releasing → released."""
        m = ResourceLockMachine("acquired")
        m.transition("held")
        m.transition("releasing")
        m.transition("released")

    def test_resource_lock_stolen(self):
        """held → stolen (forceful takeover)."""
        m = ResourceLockMachine("held")
        m.transition("stolen")
        assert m.state == "stolen"

    def test_resource_lock_expired(self):
        """held → expired (TTL expiry)."""
        m = ResourceLockMachine("held")
        m.transition("expired")
        assert m.state == "expired"

    def test_unknown_initial_state(self):
        """Unknown initial state raises ValueError."""
        with pytest.raises(ValueError):
            AgentSessionMachine("nonexistent")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. AGENT COORDINATOR
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentCoordinator:
    """Test session lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_session_creates_record(self):
        """start_session creates agent_session in 'starting' state."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "agent_session:abc",
                        "state": "starting",
                        "product": "product:test",
                    }
                ]
            ]
        )

        with patch("core.engine.live.coordinator.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            from core.engine.live.coordinator import AgentCoordinator

            coord = AgentCoordinator(db_pool=_make_pool(db))
            session = await coord.start_session(product_id="product:test", work_item_id="wi:1")

        assert session["state"] == "starting"
        assert db.query.call_count == 1
        assert "agent_session" in db.query.call_args_list[0][0][0]

    @pytest.mark.asyncio
    async def test_transition_validates_state_machine(self):
        """transition() validates via AgentSessionMachine before DB update."""
        db = AsyncMock()

        call_count = 0

        async def db_query(query, params=None):
            nonlocal call_count
            call_count += 1
            if "SELECT" in query:
                return [[{"id": "agent_session:abc", "state": "starting", "product": "product:test"}]]
            return [[{"id": "agent_session:abc", "state": "active"}]]

        db.query = AsyncMock(side_effect=db_query)

        with patch("core.engine.live.coordinator.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            from core.engine.live.coordinator import AgentCoordinator

            coord = AgentCoordinator(db_pool=_make_pool(db))
            result = await coord.transition("agent_session:abc", "active")

        assert result["state"] == "active"

    @pytest.mark.asyncio
    async def test_transition_rejects_invalid(self):
        """transition() raises InvalidTransition for invalid state change."""
        db = AsyncMock()
        db.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "agent_session:abc",
                        "state": "starting",
                        "product": "product:test",
                    }
                ]
            ]
        )

        with patch("core.engine.live.coordinator.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            from core.engine.live.coordinator import AgentCoordinator

            coord = AgentCoordinator(db_pool=_make_pool(db))

            with pytest.raises(InvalidTransition):
                await coord.transition("agent_session:abc", "done")

    @pytest.mark.asyncio
    async def test_transition_sets_completed_at_for_terminal(self):
        """Terminal transitions (done, failed, abandoned) set completed_at."""
        db = AsyncMock()

        async def db_query(query, params=None):
            if "SELECT" in query:
                return [[{"id": "agent_session:abc", "state": "completing", "product": "product:test"}]]
            return [[{"id": "agent_session:abc", "state": "done"}]]

        db.query = AsyncMock(side_effect=db_query)

        with patch("core.engine.live.coordinator.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            from core.engine.live.coordinator import AgentCoordinator

            coord = AgentCoordinator(db_pool=_make_pool(db))
            await coord.transition("agent_session:abc", "done")

        # The UPDATE query should contain completed_at
        update_call = [c for c in db.query.call_args_list if "UPDATE" in c[0][0]][0]
        assert "completed_at" in update_call[0][0]

    @pytest.mark.asyncio
    async def test_heartbeat_updates_timestamp(self):
        """heartbeat() updates last_heartbeat and optional progress_pct."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])

        from core.engine.live.coordinator import AgentCoordinator

        coord = AgentCoordinator(db_pool=_make_pool(db))

        await coord.heartbeat("agent_session:abc", progress_pct=50)

        query = db.query.call_args_list[0][0][0]
        assert "last_heartbeat" in query
        assert "progress_pct" in query


# ═══════════════════════════════════════════════════════════════════════════════
# 6. EDIT TRACKER
# ═══════════════════════════════════════════════════════════════════════════════


class TestEditTracker:
    """Test file claim and conflict detection."""

    @pytest.mark.asyncio
    async def test_claim_file_no_conflict(self):
        """claim_file succeeds when no existing claims on the file."""
        call_count = 0

        async def db_query(query, params=None):
            nonlocal call_count
            call_count += 1
            if "SELECT" in query and "active_edit" in query:
                return [[]]  # no existing claims
            if "CREATE active_edit" in query:
                return [[{"id": "active_edit:1", "state": "claimed", "file": "file:test"}]]
            return [[]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=db_query)

        with patch("core.engine.live.edit_tracker.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            from core.engine.live.edit_tracker import EditTracker

            tracker = EditTracker(db_pool=_make_pool(db))
            result = await tracker.claim_file(
                product_id="product:test",
                session_id="agent_session:abc",
                file_id="file:test",
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_release_all_releases_active_edits(self):
        """release_all directly updates all active edits to 'released'."""

        async def db_query(query, params=None):
            if "SELECT" in query and "active_edit" in query:
                return [
                    [
                        {"id": "active_edit:1", "state": "claimed"},
                        {"id": "active_edit:2", "state": "editing"},
                    ]
                ]
            if "UPDATE" in query:
                return [[{"id": "active_edit:x", "state": "released"}]]
            return [[]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=db_query)

        with patch("core.engine.live.edit_tracker.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            from core.engine.live.edit_tracker import EditTracker

            tracker = EditTracker(db_pool=_make_pool(db))

            count = await tracker.release_all("agent_session:abc", "product:test")

        assert count == 2

        # Should have: 1 SELECT + 2 UPDATEs = 3 DB calls
        update_queries = [c for c in db.query.call_args_list if "UPDATE" in c[0][0]]
        assert len(update_queries) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 7. FULL E2E WITH SURREALDB
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestFullE2EWithDB:
    """End-to-end tests requiring live SurrealDB."""

    @pytest.mark.asyncio
    async def test_initiative_to_execution(self, db_pool):
        """Full flow: create initiative → activate → decompose → execute plan."""
        from core.engine.pm.tracker import InitiativeTracker

        tracker = InitiativeTracker(db_pool=db_pool)

        # 1. Create initiative
        init = await tracker.create_initiative(
            title="E2E Pipeline Test",
            description="Test the full pipeline from initiative to execution",
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
            priority="high",
        )
        init_id = init.get("id", "")
        assert init_id, "Initiative should have an ID"
        assert init.get("status") == "planning"

        try:
            # 2. Activate
            result = await tracker.activate_initiative(init_id, "product:test")
            assert result["status"] == "active"

            # 3. Execute a plan against this initiative (mocked LLM)
            from core.engine.product.agent_orchestrator import AgentOrchestrator

            plan = {
                "spec_id": "agent_spec:e2e_test",
                "units": [
                    {
                        "id": "u1",
                        "title": "Build feature",
                        "description": "Create the feature",
                        "depends_on": [],
                        "archetype": "creator",
                        "mode": "deliberative",
                        "files_create": [],
                        "files_modify": [],
                    },
                    {
                        "id": "u2",
                        "title": "Test feature",
                        "description": "Write tests",
                        "depends_on": ["u1"],
                        "archetype": "sentinel",
                        "mode": "procedural",
                        "files_create": [],
                        "files_modify": [],
                    },
                ],
                "batches": [
                    {"task_ids": ["u1"], "mode": "sequential"},
                    {"task_ids": ["u2"], "mode": "sequential"},
                ],
                "conflicts": [],
            }

            with patch(
                "core.engine.orchestrator.executor.execute_task",
                new_callable=AsyncMock,
                return_value={"id": "task:e2e", "output": "done"},
            ):
                orch = AgentOrchestrator(db_pool=db_pool)
                summary = await orch.execute_plan(plan, product_id="product:test")

            assert summary["completed"] == 2
            assert summary["failed"] == 0

            # 4. Complete initiative
            result = await tracker.complete_initiative(init_id, "product:test")
            assert result["status"] == "completed"

        finally:
            # Cleanup
            async with db_pool.connection() as db:
                await db.query("DELETE $id", {"id": init_id})

    @pytest.mark.asyncio
    async def test_coordinator_session_lifecycle(self, db_pool):
        """Full coordinator lifecycle: start → active → completing → done."""
        with patch("core.engine.live.coordinator.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            from core.engine.live.coordinator import AgentCoordinator

            coord = AgentCoordinator(db_pool=db_pool)

            # Start session
            session = await coord.start_session(product_id="product:test")
            session_id = str(session.get("id", ""))
            assert session_id
            assert session.get("state") == "starting"

            try:
                # Transition through lifecycle
                await coord.transition(session_id, "active")
                await coord.heartbeat(session_id, progress_pct=50)
                await coord.transition(session_id, "completing")
                result = await coord.transition(session_id, "done")

                assert result.get("state") == "done"

                # Verify events were emitted
                assert mock_bus.emit.call_count >= 4  # start + 3 transitions

            finally:
                async with db_pool.connection() as db:
                    await db.query("DELETE $id", {"id": session_id})

    @pytest.mark.asyncio
    async def test_coordinator_invalid_transition_rejected(self, db_pool):
        """Coordinator rejects invalid state transitions in DB."""
        with patch("core.engine.live.coordinator.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            from core.engine.live.coordinator import AgentCoordinator

            coord = AgentCoordinator(db_pool=db_pool)
            session = await coord.start_session(product_id="product:test")
            session_id = str(session.get("id", ""))

            try:
                with pytest.raises(InvalidTransition):
                    await coord.transition(session_id, "done")  # can't skip to done
            finally:
                async with db_pool.connection() as db:
                    await db.query("DELETE $id", {"id": session_id})

    @pytest.mark.asyncio
    async def test_coordinator_active_sessions_query(self, db_pool):
        """get_active_sessions returns non-terminal sessions."""
        with patch("core.engine.live.coordinator.bus") as mock_bus:
            mock_bus.emit = AsyncMock()

            from core.engine.live.coordinator import AgentCoordinator

            coord = AgentCoordinator(db_pool=db_pool)

            # Create two sessions
            s1 = await coord.start_session(product_id="product:test")
            s2 = await coord.start_session(product_id="product:test")
            s1_id = str(s1.get("id", ""))
            s2_id = str(s2.get("id", ""))

            try:
                # Transition s1 to active, leave s2 as starting
                await coord.transition(s1_id, "active")

                active = await coord.get_active_sessions("product:test")
                active_ids = {str(s["id"]) for s in active}

                assert s1_id in active_ids
                assert s2_id in active_ids

                # Complete s1 — should disappear from active
                await coord.transition(s1_id, "completing")
                await coord.transition(s1_id, "done")

                active = await coord.get_active_sessions("product:test")
                active_ids = {str(s["id"]) for s in active}
                assert s1_id not in active_ids
                assert s2_id in active_ids

            finally:
                async with db_pool.connection() as db:
                    await db.query("DELETE $id", {"id": s1_id})
                    await db.query("DELETE $id", {"id": s2_id})
