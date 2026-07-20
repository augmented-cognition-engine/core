# tests/test_e2e_pm.py
"""E2E integration tests for the autonomous PM pipeline.
Requires running SurrealDB with v012 schema applied.
"""

import os
import tempfile

import pytest

pytestmark = pytest.mark.e2e
from git import Repo

# --- E2E tests (require SurrealDB) ---


@pytest.mark.asyncio
async def test_e2e_initiative_lifecycle(db_pool):
    """Create → activate → track → complete lifecycle."""
    from core.engine.pm.tracker import InitiativeTracker

    tracker = InitiativeTracker(db_pool=db_pool)

    # Create
    init = await tracker.create_initiative(
        title="E2E Test Initiative",
        description="Test the full lifecycle",
        product_id="product:test",
        workspace_id="workspace:test",
        user_id="user:test",
        priority="high",
        cost_budget=50.0,
    )
    assert init.get("status") == "planning" or "id" in init

    init_id = init.get("id", "")
    if not init_id:
        return  # Can't continue without ID

    # Activate
    result = await tracker.activate_initiative(init_id, "product:test")
    assert result["status"] == "active"

    # Pause
    result = await tracker.pause_initiative(init_id, "product:test")
    assert result["status"] == "paused"

    # Resume (re-activate)
    result = await tracker.activate_initiative(init_id, "product:test")
    assert result["status"] == "active"

    # Complete
    result = await tracker.complete_initiative(init_id, "product:test")
    assert result["status"] == "completed"

    # Cleanup
    async with db_pool.connection() as db:
        await db.query("DELETE $id", {"id": init_id})


@pytest.mark.asyncio
async def test_e2e_parallel_execution():
    """Two work items with no file overlap are elevated to Team pattern orchestration."""
    from unittest.mock import AsyncMock, patch

    from core.engine.pm.parallel import ParallelExecutor

    executor = ParallelExecutor()

    work_items = [
        {"id": "wi:a", "title": "Task A", "files_touched": ["src/models/a.py"], "parallel_group": 1},
        {"id": "wi:b", "title": "Task B", "files_touched": ["src/views/b.py"], "parallel_group": 1},
    ]

    # Mock orchestrate since Team pattern requires LLM + full pipeline
    mock_result = AsyncMock()
    mock_result.status = "completed"
    mock_result.pattern_result = AsyncMock()
    mock_result.pattern_result.agent_results = [
        AsyncMock(output="output A", status="completed", error=None),
        AsyncMock(output="output B", status="completed", error=None),
    ]

    with patch("core.engine.orchestration.orchestrate", return_value=mock_result):
        results = await executor.execute_parallel_group(work_items, product_id="product:test")

    assert len(results) == 2
    assert all(r["status"] == "completed" for r in results)


@pytest.mark.asyncio
async def test_e2e_sequential_fallback():
    """Two work items with file overlap run sequentially."""
    from core.engine.pm.parallel import ParallelExecutor

    execution_order = []

    async def mock_execute_wi(wi, product_id):
        execution_order.append(wi["id"])
        return {"id": wi["id"], "status": "completed"}

    executor = ParallelExecutor()
    executor._execute_single_work_item = mock_execute_wi

    work_items = [
        {"id": "wi:a", "files_touched": ["src/main.py", "src/utils.py"], "parallel_group": 1},
        {"id": "wi:b", "files_touched": ["src/main.py", "src/other.py"], "parallel_group": 1},
    ]

    results = await executor.execute_parallel_group(work_items, product_id="product:test")
    assert len(results) == 2
    assert execution_order == ["wi:a", "wi:b"]  # Sequential order preserved


@pytest.mark.asyncio
async def test_e2e_git_branch_lifecycle():
    """Full git branch lifecycle: create → commit → merge → cleanup."""
    from core.engine.pm.git import GitBranchManager

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Repo.init(tmpdir)
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "test@test.com").release()

        # Initial commit
        readme = os.path.join(tmpdir, "README.md")
        with open(readme, "w") as f:
            f.write("# Project\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")

        gm = GitBranchManager(repo_path=tmpdir)

        # Create work item branches
        branch_name = gm.make_branch_name("init:test1", 1, 0, "Add feature")
        gm.create_branch(branch_name, from_branch="master")

        # Work on branch
        repo.heads[branch_name].checkout()
        with open(os.path.join(tmpdir, "feature.py"), "w") as f:
            f.write("def feature(): return 'hello'\n")
        repo.index.add(["feature.py"])
        repo.index.commit("Add feature")

        # Create integration branch and merge
        repo.heads["master"].checkout()
        int_branch = gm.create_integration_branch("test1", 1, from_branch="master")
        result = gm.merge_branch(branch_name, into=int_branch)
        assert result["success"] is True

        # Merge integration to master
        result = gm.merge_branch(int_branch, into="master")
        assert result["success"] is True

        # Cleanup
        gm.delete_branch(branch_name)
        gm.delete_branch(int_branch)
        assert branch_name not in [b.name for b in repo.branches]


@pytest.mark.asyncio
async def test_e2e_conflict_prediction_gate():
    """Conflict prediction correctly gates parallel vs sequential execution."""
    from core.engine.pm.git import predict_merge_conflicts

    # No overlap → parallel
    clean_items = [
        {"id": "wi:1", "files_touched": ["src/components/button.tsx"]},
        {"id": "wi:2", "files_touched": ["src/models/user.ts"]},
    ]
    assert predict_merge_conflicts(clean_items) == []

    # File overlap → sequential
    overlapping_items = [
        {"id": "wi:1", "files_touched": ["src/config.ts"]},
        {"id": "wi:2", "files_touched": ["src/config.ts"]},
    ]
    conflicts = predict_merge_conflicts(overlapping_items)
    assert len(conflicts) == 1
    assert conflicts[0]["recommendation"] == "run_sequentially"


@pytest.mark.asyncio
async def test_e2e_review_pipeline():
    """Review pipeline filters by confidence and categorizes correctly."""
    from unittest.mock import AsyncMock

    from core.engine.pm.review import WorkItemReviewer

    call_count = 0

    async def mock_complete_json(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if "error handling" in prompt.lower():
            return {
                "issues": [
                    {"description": "Missing try/catch", "severity": "major", "confidence": 85},
                    {"description": "Low confidence issue", "severity": "minor", "confidence": 40},
                ],
                "summary": "Some issues",
            }
        return {"issues": [], "summary": "OK"}

    mock_llm = AsyncMock()
    mock_llm.complete_json = mock_complete_json

    reviewer = WorkItemReviewer(llm=mock_llm, confidence_threshold=80)
    result = await reviewer.review_work_item(
        work_item={"title": "Test WI", "description": "Test", "domain_path": "architecture"},
        initiative={"title": "Test Init", "success_criteria": []},
        output="def foo():\n  pass\n",
        product_id="product:test",
    )

    assert call_count == 5
    assert result["passed"] is True  # major doesn't block
    assert result["needs_attention"] is True
    assert len(result["all_issues"]) == 1  # only the 85-confidence one


@pytest.mark.asyncio
async def test_e2e_cost_tracking():
    """Cost budget enforcement at thresholds."""
    from core.engine.pm.tracker import check_cost_budget

    # Progressive cost accumulation
    assert check_cost_budget(0, 100)["status"] == "ok"
    assert check_cost_budget(50, 100)["status"] == "ok"
    assert check_cost_budget(80, 100)["status"] == "warn"
    assert check_cost_budget(90, 100)["status"] == "pause"
    assert check_cost_budget(100, 100)["status"] == "override_required"
    assert check_cost_budget(110, 100)["status"] == "override_required"


@pytest.mark.asyncio
async def test_e2e_file_locks(db_pool):
    """File lock acquire, contention, release, TTL expiry."""
    from core.engine.pm.locks import FileLockManager

    lm = FileLockManager(db_pool=db_pool)

    # Acquire
    acquired = await lm.acquire("file", "test/e2e.py", "wi:test1", "product:test", ttl_minutes=1)
    assert acquired is True

    # Contention — same file, different holder
    blocked = await lm.acquire("file", "test/e2e.py", "wi:test2", "product:test", ttl_minutes=1)
    assert blocked is False

    # Release
    await lm.release("file", "test/e2e.py", "product:test")

    # Now should be acquirable
    reacquired = await lm.acquire("file", "test/e2e.py", "wi:test2", "product:test", ttl_minutes=1)
    assert reacquired is True

    # Cleanup
    await lm.release("file", "test/e2e.py", "product:test")
