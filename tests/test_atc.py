# tests/test_atc.py
"""Tests for the ATC (Air Traffic Control) execution model.

Covers:
- AirspaceAssigner: graph/directory/prediction fallback, overlap resolution
- WorktreeManager: create/merge/cleanup lifecycle
- Context threading: prior_context flows between sequential units
- ATCMonitor: violation detection, inject_message warnings
- EditTracker: airspace violation check in claim_file
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.orchestration.airspace import AirspaceAssigner, AirspaceAssignment, _glob_matches
from core.engine.orchestration.atc_monitor import ATCMonitor
from core.engine.orchestration.bus import BusMessage
from core.engine.product.agent_orchestrator import AgentOrchestrator, UnitContext, _format_prior_context

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
# 1. AIRSPACE ASSIGNER
# ═══════════════════════════════════════════════════════════════════════════════


class TestGlobMatching:
    """Test the _glob_matches helper used for directory fallback."""

    def test_double_star_matches_subdirectory(self):
        assert _glob_matches("engine/orchestrator/executor.py", "engine/orchestrator/**")

    def test_double_star_matches_nested(self):
        assert _glob_matches("engine/orchestrator/sub/deep.py", "engine/orchestrator/**")

    def test_double_star_no_match(self):
        assert not _glob_matches("engine/core/db.py", "engine/orchestrator/**")

    def test_fnmatch_pattern(self):
        assert _glob_matches("test_foo.py", "test_*.py")

    def test_fnmatch_no_match(self):
        assert not _glob_matches("foo.py", "test_*.py")


class TestAirspaceAssignerPredictionFallback:
    """When graph has no data, falls back to raw LLM predictions."""

    @pytest.mark.asyncio
    async def test_empty_units(self):
        assigner = AirspaceAssigner(db_pool=_make_pool())
        result = await assigner.assign([], "product:test")
        assert result == {}

    @pytest.mark.asyncio
    async def test_prediction_fallback_when_graph_empty(self):
        """No graph_file nodes → falls back to raw predictions."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])  # empty graph

        assigner = AirspaceAssigner(db_pool=_make_pool(db))

        units = [
            {"id": "u1", "files_create": ["src/auth.py"], "files_modify": []},
            {"id": "u2", "files_create": ["src/billing.py"], "files_modify": []},
        ]

        result = await assigner.assign(units, "product:test")

        assert "u1" in result
        assert "u2" in result
        assert "src/auth.py" in result["u1"].owned_files
        assert "src/billing.py" in result["u2"].owned_files
        # Prediction or directory fallback
        assert result["u1"].source in ("prediction", "directory")

    @pytest.mark.asyncio
    async def test_units_with_no_files(self):
        """Units with no predicted files get empty assignments."""
        assigner = AirspaceAssigner(db_pool=_make_pool())

        units = [
            {"id": "u1", "files_create": [], "files_modify": []},
        ]

        result = await assigner.assign(units, "product:test")
        assert result["u1"].owned_files == set()


class TestAirspaceAssignerDirectoryFallback:
    """When graph is empty but directory patterns match."""

    @pytest.mark.asyncio
    async def test_directory_fallback_matches(self):
        """Files in known directories get assigned to capability globs."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        assigner = AirspaceAssigner(db_pool=_make_pool(db))

        units = [
            {"id": "u1", "files_create": ["engine/orchestrator/new_module.py"], "files_modify": []},
        ]

        result = await assigner.assign(units, "product:test")

        assert result["u1"].source == "directory"
        assert "intelligence_pipeline" in result["u1"].capability_slugs


class TestAirspaceAssignerGraphPath:
    """When graph has realizes edges, expand via capabilities."""

    @pytest.mark.asyncio
    async def test_graph_expands_to_capability_files(self):
        """Graph realizes edges expand ownership to all files in the capability."""
        call_count = 0

        async def mock_query(query, params=None):
            nonlocal call_count
            call_count += 1

            if "graph_file WHERE path IN" in query:
                return [[{"id": "graph_file:auth", "path": "engine/auth.py"}]]
            elif "realizes WHERE in =" in query:
                return [[{"out": "capability:auth_system", "slug": "auth_system"}]]
            elif "realizes WHERE out =" in query:
                return [
                    [
                        {"path": "engine/auth.py"},
                        {"path": "engine/auth_middleware.py"},
                        {"path": "engine/jwt_utils.py"},
                    ]
                ]
            elif "imports" in query:
                return [[{"paths": ["core/engine/core/config.py"]}]]
            return [[]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=mock_query)

        assigner = AirspaceAssigner(db_pool=_make_pool(db))

        units = [
            {"id": "u1", "files_create": [], "files_modify": ["engine/auth.py"]},
        ]

        result = await assigner.assign(units, "product:test")

        assert result["u1"].source == "graph"
        assert "engine/auth.py" in result["u1"].owned_files
        assert "engine/auth_middleware.py" in result["u1"].owned_files
        assert "engine/jwt_utils.py" in result["u1"].owned_files
        assert "core/engine/core/config.py" in result["u1"].owned_files  # import neighbor
        assert "auth_system" in result["u1"].capability_slugs


class TestAirspaceOverlapResolution:
    """When two units claim the same file."""

    @pytest.mark.asyncio
    async def test_direct_prediction_wins(self):
        """Unit that directly predicted a file wins; other gets boundary."""
        assigner = AirspaceAssigner(db_pool=_make_pool())

        # Manually create overlapping assignments
        assignments = {
            "u1": AirspaceAssignment(
                unit_id="u1",
                owned_files={"shared.py", "a.py"},
                source="graph",
            ),
            "u2": AirspaceAssignment(
                unit_id="u2",
                owned_files={"shared.py", "b.py"},
                source="graph",
            ),
        }

        unit_files = {
            "u1": {"shared.py", "a.py"},  # u1 directly predicted shared.py
            "u2": {"b.py"},  # u2 did NOT directly predict shared.py
        }

        result = assigner._resolve_overlaps(assignments, unit_files)

        assert "shared.py" in result["u1"].owned_files
        assert "shared.py" not in result["u2"].owned_files
        assert "shared.py" in result["u2"].boundary_files

    @pytest.mark.asyncio
    async def test_no_overlap_no_change(self):
        """Non-overlapping assignments pass through unchanged."""
        assigner = AirspaceAssigner(db_pool=_make_pool())

        assignments = {
            "u1": AirspaceAssignment(unit_id="u1", owned_files={"a.py"}),
            "u2": AirspaceAssignment(unit_id="u2", owned_files={"b.py"}),
        }

        result = assigner._resolve_overlaps(assignments, {"u1": {"a.py"}, "u2": {"b.py"}})

        assert result["u1"].owned_files == {"a.py"}
        assert result["u2"].owned_files == {"b.py"}
        assert len(result["u1"].boundary_files) == 0
        assert len(result["u2"].boundary_files) == 0

    @pytest.mark.asyncio
    async def test_line_number_stripping(self):
        """File references with line numbers are stripped."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        assigner = AirspaceAssigner(db_pool=_make_pool(db))

        units = [
            {"id": "u1", "files_create": ["src/auth.py:1-50"], "files_modify": ["src/config.py:100"]},
        ]

        result = await assigner.assign(units, "product:test")
        assert "src/auth.py" in result["u1"].owned_files
        assert "src/config.py" in result["u1"].owned_files


class TestMultiSessionAirspace:
    """Test cross-session ATC: files claimed by other sessions are excluded."""

    @pytest.mark.asyncio
    async def test_occupied_files_moved_to_boundary(self):
        """Files claimed by other active sessions become boundary, not owned."""

        async def mock_query(query, params=None):
            if "active_edit" in query:
                # Another session has claimed config.py
                return [[{"file": "engine/config.py"}]]
            if "graph_file WHERE path IN" in query:
                return [[]]  # no graph data → prediction fallback
            return [[]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=mock_query)

        assigner = AirspaceAssigner(db_pool=_make_pool(db))

        units = [
            {"id": "u1", "files_create": [], "files_modify": ["engine/config.py", "engine/auth.py"]},
        ]

        result = await assigner.assign(units, "product:test")

        # config is occupied by another session → boundary
        assert "engine/config.py" in result["u1"].boundary_files
        # auth.py is free → owned
        assert "engine/auth.py" in result["u1"].owned_files

    @pytest.mark.asyncio
    async def test_exclude_own_sessions(self):
        """exclude_sessions parameter prevents self-conflicts."""

        async def mock_query(query, params=None):
            if "active_edit" in query:
                # Check that exclude param was passed
                assert "exclude" in (params or {}), "Should pass exclude_sessions"
                return [[]]  # nothing from other sessions
            return [[]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=mock_query)

        assigner = AirspaceAssigner(db_pool=_make_pool(db))

        units = [
            {"id": "u1", "files_create": ["new.py"], "files_modify": []},
        ]

        result = await assigner.assign(
            units,
            "product:test",
            exclude_sessions=["agent_session:my_session"],
        )

        assert "new.py" in result["u1"].owned_files

    @pytest.mark.asyncio
    async def test_no_occupied_files_no_change(self):
        """When no other sessions are active, assignments are unaffected."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])  # no active edits

        assigner = AirspaceAssigner(db_pool=_make_pool(db))

        units = [
            {"id": "u1", "files_create": ["a.py"], "files_modify": ["b.py"]},
        ]

        result = await assigner.assign(units, "product:test")

        assert "a.py" in result["u1"].owned_files
        assert "b.py" in result["u1"].owned_files
        assert len(result["u1"].boundary_files) == 0

    @pytest.mark.asyncio
    async def test_occupied_query_failure_graceful(self):
        """DB failure in occupied query doesn't crash — proceeds without exclusion."""
        call_count = 0

        async def mock_query(query, params=None):
            nonlocal call_count
            call_count += 1
            if "active_edit" in query:
                raise RuntimeError("DB connection lost")
            return [[]]

        db = AsyncMock()
        db.query = AsyncMock(side_effect=mock_query)

        assigner = AirspaceAssigner(db_pool=_make_pool(db))

        units = [
            {"id": "u1", "files_create": ["safe.py"], "files_modify": []},
        ]

        # Should not raise
        result = await assigner.assign(units, "product:test")
        assert "safe.py" in result["u1"].owned_files

    def test_exclude_occupied_moves_to_boundary(self):
        """_exclude_occupied moves occupied files from owned → boundary."""
        assigner = AirspaceAssigner(db_pool=_make_pool())

        assignments = {
            "u1": AirspaceAssignment(
                unit_id="u1",
                owned_files={"a.py", "b.py", "shared.py"},
            ),
        }

        result = assigner._exclude_occupied(assignments, occupied={"shared.py"})

        assert "shared.py" not in result["u1"].owned_files
        assert "shared.py" in result["u1"].boundary_files
        assert "a.py" in result["u1"].owned_files
        assert "b.py" in result["u1"].owned_files


# ═══════════════════════════════════════════════════════════════════════════════
# 2. WORKTREE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorktreeManager:
    """Test git worktree create/merge/cleanup lifecycle."""

    @pytest.mark.asyncio
    async def test_create_for_batch(self):
        """create_for_batch creates one worktree per unit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from git import Repo

            repo = Repo.init(tmpdir)
            repo.config_writer().set_value("user", "name", "Test").release()
            repo.config_writer().set_value("user", "email", "test@test.com").release()

            # Initial commit required for worktrees
            readme = os.path.join(tmpdir, "README.md")
            with open(readme, "w") as f:
                f.write("# Test\n")
            repo.index.add(["README.md"])
            repo.index.commit("Initial commit")

            from core.engine.orchestration.worktree_manager import WorktreeManager

            mgr = WorktreeManager(repo_path=tmpdir)
            worktrees = await mgr.create_for_batch(["unit-1", "unit-2"])

            assert len(worktrees) == 2
            assert os.path.isdir(worktrees["unit-1"].worktree_path)
            assert os.path.isdir(worktrees["unit-2"].worktree_path)
            assert worktrees["unit-1"].branch_name == "atc/unit-1"
            assert worktrees["unit-2"].branch_name == "atc/unit-2"

            # Verify files exist in worktrees
            assert os.path.isfile(os.path.join(worktrees["unit-1"].worktree_path, "README.md"))

            # Cleanup
            await mgr.cleanup_batch(["unit-1", "unit-2"])

    @pytest.mark.asyncio
    async def test_merge_batch(self):
        """merge_batch merges unit branches into integration branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from git import Repo

            repo = Repo.init(tmpdir)
            repo.config_writer().set_value("user", "name", "Test").release()
            repo.config_writer().set_value("user", "email", "test@test.com").release()

            readme = os.path.join(tmpdir, "README.md")
            with open(readme, "w") as f:
                f.write("# Test\n")
            repo.index.add(["README.md"])
            repo.index.commit("Initial commit")

            from core.engine.orchestration.worktree_manager import WorktreeManager

            mgr = WorktreeManager(repo_path=tmpdir)
            worktrees = await mgr.create_for_batch(["unit-1", "unit-2"])

            # Make changes in each worktree
            wt1_path = worktrees["unit-1"].worktree_path
            wt2_path = worktrees["unit-2"].worktree_path

            with open(os.path.join(wt1_path, "feature_a.py"), "w") as f:
                f.write("def feature_a(): pass\n")
            wt1_repo = Repo(wt1_path)
            wt1_repo.index.add(["feature_a.py"])
            wt1_repo.index.commit("Add feature A")

            with open(os.path.join(wt2_path, "feature_b.py"), "w") as f:
                f.write("def feature_b(): pass\n")
            wt2_repo = Repo(wt2_path)
            wt2_repo.index.add(["feature_b.py"])
            wt2_repo.index.commit("Add feature B")

            # Merge
            result = await mgr.merge_batch(["unit-1", "unit-2"], "atc/integration")

            assert len(result["merged"]) == 2
            assert len(result["conflicts"]) == 0

            # Cleanup
            await mgr.cleanup_batch(["unit-1", "unit-2"])

    @pytest.mark.asyncio
    async def test_cleanup_removes_worktrees(self):
        """cleanup_batch removes worktrees and deletes branches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from git import Repo

            repo = Repo.init(tmpdir)
            repo.config_writer().set_value("user", "name", "Test").release()
            repo.config_writer().set_value("user", "email", "test@test.com").release()

            readme = os.path.join(tmpdir, "README.md")
            with open(readme, "w") as f:
                f.write("# Test\n")
            repo.index.add(["README.md"])
            repo.index.commit("Initial commit")

            from core.engine.orchestration.worktree_manager import WorktreeManager

            mgr = WorktreeManager(repo_path=tmpdir)
            worktrees = await mgr.create_for_batch(["unit-cleanup"])

            wt_path = worktrees["unit-cleanup"].worktree_path
            assert os.path.isdir(wt_path)

            await mgr.cleanup_batch(["unit-cleanup"])

            assert not os.path.isdir(wt_path)
            assert "atc/unit-cleanup" not in [b.name for b in repo.branches]

    @pytest.mark.asyncio
    async def test_get_worktree_path(self):
        """get_worktree_path returns path for active worktrees, None for unknown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from git import Repo

            repo = Repo.init(tmpdir)
            repo.config_writer().set_value("user", "name", "Test").release()
            repo.config_writer().set_value("user", "email", "test@test.com").release()
            readme = os.path.join(tmpdir, "README.md")
            with open(readme, "w") as f:
                f.write("# Test\n")
            repo.index.add(["README.md"])
            repo.index.commit("Initial commit")

            from core.engine.orchestration.worktree_manager import WorktreeManager

            mgr = WorktreeManager(repo_path=tmpdir)
            await mgr.create_for_batch(["unit-x"])

            assert mgr.get_worktree_path("unit-x") is not None
            assert mgr.get_worktree_path("nonexistent") is None

            await mgr.cleanup_batch(["unit-x"])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CONTEXT THREADING
# ═══════════════════════════════════════════════════════════════════════════════


class TestContextThreading:
    """Test prior_context flows between sequential units."""

    @pytest.mark.asyncio
    async def test_sequential_units_receive_prior_context(self):
        """When u2 depends on u1, u2 receives u1's output as prior_context."""
        pool = _make_pool()
        plan = {
            "spec_id": "agent_spec:ctx",
            "units": [
                {
                    "id": "u1",
                    "title": "Build schema",
                    "description": "Create DB schema",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": ["schema.sql"],
                    "files_modify": [],
                },
                {
                    "id": "u2",
                    "title": "Build API",
                    "description": "Create endpoints using schema",
                    "depends_on": ["u1"],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": ["api.py"],
                    "files_modify": [],
                },
            ],
            "batches": [
                {"task_ids": ["u1"], "mode": "sequential"},
                {"task_ids": ["u2"], "mode": "sequential"},
            ],
            "conflicts": [],
        }

        descriptions_received: list[str] = []

        async def mock_execute_task(description, product_id, **kwargs):
            descriptions_received.append(description)
            return {"id": "task:x", "output": "Schema created with tables user, session"}

        with patch("core.engine.orchestrator.executor.execute_task", side_effect=mock_execute_task):
            orch = AgentOrchestrator(db_pool=pool)
            await orch.execute_plan(plan, product_id="product:test")

        # u2 should have received prior context from u1
        assert len(descriptions_received) == 2
        u2_desc = descriptions_received[1]
        assert "Prior Work" in u2_desc
        assert "Build schema" in u2_desc or "u1" in u2_desc

    @pytest.mark.asyncio
    async def test_no_prior_context_for_independent_units(self):
        """Units with no dependencies get no prior_context."""
        pool = _make_pool()
        plan = {
            "spec_id": "agent_spec:independent",
            "units": [
                {
                    "id": "u1",
                    "title": "Task A",
                    "description": "Independent work",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
            ],
            "batches": [
                {"task_ids": ["u1"], "mode": "sequential"},
            ],
            "conflicts": [],
        }

        descriptions_received: list[str] = []

        async def mock_execute_task(description, product_id, **kwargs):
            descriptions_received.append(description)
            return {"id": "task:x", "output": "done"}

        with patch("core.engine.orchestrator.executor.execute_task", side_effect=mock_execute_task):
            orch = AgentOrchestrator(db_pool=pool)
            await orch.execute_plan(plan, product_id="product:test")

        assert "Prior Work" not in descriptions_received[0]

    def test_format_prior_context(self):
        """_format_prior_context produces structured prompt section."""
        contexts = [
            UnitContext(
                unit_id="u1",
                title="Build schema",
                output_summary="Created tables: user, session, token",
                files_changed=["schema.sql", "core/engine/core/db.py"],
                status="completed",
            ),
        ]

        formatted = _format_prior_context(contexts)

        assert "## Prior Work" in formatted
        assert "Build schema" in formatted
        assert "tables: user, session, token" in formatted
        assert "schema.sql" in formatted

    def test_format_prior_context_multiple(self):
        """Multiple predecessors are all included."""
        contexts = [
            UnitContext(
                unit_id="u1", title="Step 1", output_summary="Did A", files_changed=["a.py"], status="completed"
            ),
            UnitContext(
                unit_id="u2", title="Step 2", output_summary="Did B", files_changed=["b.py"], status="completed"
            ),
        ]

        formatted = _format_prior_context(contexts)

        assert "Step 1" in formatted
        assert "Step 2" in formatted
        assert "Did A" in formatted
        assert "Did B" in formatted

    @pytest.mark.asyncio
    async def test_build_prior_context_only_completed_deps(self):
        """_build_prior_context only includes completed predecessors."""
        pool = _make_pool()
        orch = AgentOrchestrator(db_pool=pool)

        # Simulate: u1 completed, u2 failed
        orch._unit_status = {"u1": "completed", "u2": "failed"}
        orch._unit_results = {
            "u1": {"title": "Setup", "output": "Done", "files_changed": []},
            "u2": {"error": "crashed"},
        }

        unit = {"depends_on": ["u1", "u2"]}
        result = orch._build_prior_context("u3", unit)

        # Should only include u1 (completed), not u2 (failed)
        assert len(result) == 1
        assert result[0].unit_id == "u1"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ATC MONITOR
# ═══════════════════════════════════════════════════════════════════════════════


class TestATCMonitor:
    """Test runtime airspace violation detection and inject_message warnings."""

    @pytest.mark.asyncio
    async def test_violation_recorded(self):
        """Violations are recorded in the monitor's violation list."""
        monitor = ATCMonitor(
            assignments={
                "u1": AirspaceAssignment(unit_id="u1", owned_files={"a.py"}),
            }
        )

        await monitor._on_airspace_violation(
            "edit.airspace_violation",
            {
                "session_id": "session:abc",
                "file": "unauthorized.py",
                "product_id": "product:test",
            },
        )

        assert len(monitor.violations) == 1
        assert monitor.violations[0]["file"] == "unauthorized.py"

    @pytest.mark.asyncio
    async def test_inject_message_on_violation(self):
        """Monitor sends inject_message warning to registered agent."""
        mock_shell = AsyncMock()
        mock_shell.inject_message = AsyncMock()

        monitor = ATCMonitor(assignments={})
        monitor.register_agent("session:abc", mock_shell)

        await monitor._on_airspace_violation(
            "edit.airspace_violation",
            {
                "session_id": "session:abc",
                "file": "forbidden.py",
            },
        )

        mock_shell.inject_message.assert_called_once()
        injected = mock_shell.inject_message.call_args[0][0]
        assert isinstance(injected, BusMessage)
        assert "forbidden.py" in injected.payload["warning"]

    @pytest.mark.asyncio
    async def test_no_inject_for_unregistered_agent(self):
        """No inject_message if agent isn't registered (no crash)."""
        monitor = ATCMonitor(assignments={})

        # Should not raise
        await monitor._on_airspace_violation(
            "edit.airspace_violation",
            {
                "session_id": "unknown:session",
                "file": "some.py",
            },
        )

        assert len(monitor.violations) == 1

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self):
        """start() registers handler, stop() unregisters it."""
        with patch("core.engine.events.bus.bus") as mock_bus:
            monitor = ATCMonitor(assignments={})

            monitor.start()
            mock_bus.on.assert_called_once_with("edit.airspace_violation", monitor._handler_ref)

            monitor.stop()
            mock_bus.off.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_violations_accumulated(self):
        """Multiple violations from different agents are all recorded."""
        monitor = ATCMonitor(assignments={})

        for i in range(5):
            await monitor._on_airspace_violation(
                "edit.airspace_violation",
                {
                    "session_id": f"session:{i}",
                    "file": f"file_{i}.py",
                },
            )

        assert len(monitor.violations) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# 5. EDIT TRACKER AIRSPACE CHECK
# ═══════════════════════════════════════════════════════════════════════════════


class TestEditTrackerAirspace:
    """Test the airspace violation check added to claim_file."""

    @pytest.mark.asyncio
    async def test_violation_emitted_for_unauthorized_file(self):
        """claim_file emits edit.airspace_violation when file not in assigned set."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        emitted_events: list[tuple] = []

        async def capture_emit(event_type, payload):
            emitted_events.append((event_type, payload))

        with patch("core.engine.live.edit_tracker.bus") as mock_bus:
            mock_bus.emit = AsyncMock(side_effect=capture_emit)

            from core.engine.live.edit_tracker import EditTracker

            tracker = EditTracker(db_pool=_make_pool(db))
            await tracker.claim_file(
                product_id="product:test",
                session_id="session:abc",
                file_id="file:unauthorized",
                assigned_files={"file:auth", "file:jwt"},
            )

        violation_events = [e for e in emitted_events if e[0] == "edit.airspace_violation"]
        assert len(violation_events) == 1
        assert violation_events[0][1]["file"] == "file:unauthorized"
        assert violation_events[0][1]["session_id"] == "session:abc"

    @pytest.mark.asyncio
    async def test_no_violation_for_authorized_file(self):
        """claim_file does NOT emit violation when file is in assigned set."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        emitted_events: list[tuple] = []

        async def capture_emit(event_type, payload):
            emitted_events.append((event_type, payload))

        with patch("core.engine.live.edit_tracker.bus") as mock_bus:
            mock_bus.emit = AsyncMock(side_effect=capture_emit)

            from core.engine.live.edit_tracker import EditTracker

            tracker = EditTracker(db_pool=_make_pool(db))
            await tracker.claim_file(
                product_id="product:test",
                session_id="session:abc",
                file_id="file:auth",
                assigned_files={"file:auth", "file:jwt"},
            )

        violation_events = [e for e in emitted_events if e[0] == "edit.airspace_violation"]
        assert len(violation_events) == 0

    @pytest.mark.asyncio
    async def test_no_check_when_no_assigned_files(self):
        """Without assigned_files param, no airspace check (backward compat)."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[]])

        emitted_events: list[tuple] = []

        async def capture_emit(event_type, payload):
            emitted_events.append((event_type, payload))

        with patch("core.engine.live.edit_tracker.bus") as mock_bus:
            mock_bus.emit = AsyncMock(side_effect=capture_emit)

            from core.engine.live.edit_tracker import EditTracker

            tracker = EditTracker(db_pool=_make_pool(db))
            await tracker.claim_file(
                product_id="product:test",
                session_id="session:abc",
                file_id="file:anything",
                # No assigned_files — backward compatible
            )

        violation_events = [e for e in emitted_events if e[0] == "edit.airspace_violation"]
        assert len(violation_events) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. ORCHESTRATOR ATC INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorATCIntegration:
    """Test AgentOrchestrator with ATC components wired in."""

    @pytest.mark.asyncio
    async def test_orchestrator_accepts_atc_params(self):
        """AgentOrchestrator accepts airspace_assigner."""
        pool = _make_pool()
        orch = AgentOrchestrator(
            db_pool=pool,
            airspace_assigner=MagicMock(),
        )
        assert orch._airspace is not None

    @pytest.mark.asyncio
    async def test_orchestrator_without_atc_backward_compat(self):
        """AgentOrchestrator works without ATC params (existing behavior)."""
        pool = _make_pool()
        plan = {
            "spec_id": "agent_spec:compat",
            "units": [
                {
                    "id": "u1",
                    "title": "Task",
                    "description": "Do work",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
            ],
            "batches": [{"task_ids": ["u1"], "mode": "sequential"}],
            "conflicts": [],
        }

        with patch(
            "core.engine.orchestrator.executor.execute_task",
            new_callable=AsyncMock,
            return_value={"id": "task:1", "output": "done"},
        ):
            orch = AgentOrchestrator(db_pool=pool)
            summary = await orch.execute_plan(plan, product_id="product:test")

        assert summary["completed"] == 1

    @pytest.mark.asyncio
    async def test_execute_unit_passes_workspace_and_user(self):
        """_execute_unit now passes workspace_id and user_id (bug fix)."""
        pool = _make_pool()
        captured_kwargs: list[dict] = []

        async def mock_execute_task(**kwargs):
            captured_kwargs.append(kwargs)
            return {"id": "task:1", "output": "done"}

        with patch("core.engine.orchestrator.executor.execute_task", side_effect=mock_execute_task):
            orch = AgentOrchestrator(db_pool=pool)
            await orch._execute_unit(
                "u1",
                {"title": "Test", "description": "Do something", "files_create": [], "files_modify": []},
                "product:test",
            )

        assert len(captured_kwargs) == 1
        assert "workspace_id" in captured_kwargs[0]
        assert "user_id" in captured_kwargs[0]
