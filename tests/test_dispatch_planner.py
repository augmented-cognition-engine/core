# tests/test_dispatch_planner.py
"""Tests for plan task dispatch planner."""

from core.engine.orchestration.dispatch_planner import (
    DispatchSchedule,
    _extract_files,
    format_schedule,
    plan_dispatch,
)


def test_extract_files_all_sources():
    task = {
        "files_create": ["engine/foo.py"],
        "files_modify": ["engine/bar.py:123-145"],
        "files_test": ["tests/test_foo.py"],
    }
    files = _extract_files(task)
    assert files == {"engine/foo.py", "engine/bar.py", "tests/test_foo.py"}


def test_extract_files_strips_line_numbers():
    task = {"files_modify": ["engine/api/tasks.py:90-95"]}
    files = _extract_files(task)
    assert files == {"engine/api/tasks.py"}


def test_independent_tasks_parallel():
    tasks = [
        {"id": "t1", "files_create": ["engine/a.py"], "files_modify": [], "depends_on": []},
        {"id": "t2", "files_create": ["engine/b.py"], "files_modify": [], "depends_on": []},
        {"id": "t3", "files_create": ["engine/c.py"], "files_modify": [], "depends_on": []},
    ]
    schedule = plan_dispatch(tasks)
    assert len(schedule.batches) == 1
    assert schedule.batches[0].mode == "parallel"
    assert set(schedule.batches[0].task_ids) == {"t1", "t2", "t3"}


def test_dependent_tasks_sequential():
    tasks = [
        {"id": "t1", "files_create": ["schema/v025.surql"], "depends_on": []},
        {"id": "t2", "files_create": ["engine/a.py"], "depends_on": ["t1"]},
        {"id": "t3", "files_create": ["engine/b.py"], "depends_on": ["t1"]},
    ]
    schedule = plan_dispatch(tasks)
    # t1 must go first, then t2+t3 can be parallel
    assert schedule.batches[0].task_ids == ["t1"]
    assert len(schedule.batches) >= 2
    # t2 and t3 should be in a parallel batch after t1
    later_tasks = set()
    for batch in schedule.batches[1:]:
        later_tasks.update(batch.task_ids)
    assert "t2" in later_tasks
    assert "t3" in later_tasks


def test_file_conflict_forces_sequential():
    tasks = [
        {"id": "t1", "files_modify": ["engine/executor.py"], "depends_on": []},
        {"id": "t2", "files_modify": ["engine/executor.py"], "depends_on": []},
    ]
    schedule = plan_dispatch(tasks)
    # Both touch executor.py — can't be parallel
    assert not any(b.mode == "parallel" and len(b.task_ids) >= 2 for b in schedule.batches)


def test_mixed_parallel_and_sequential():
    tasks = [
        {"id": "schema", "files_create": ["schema/v025.surql"], "depends_on": []},
        {"id": "models", "files_create": ["engine/models.py"], "depends_on": ["schema"]},
        {"id": "resolver", "files_create": ["engine/resolver.py"], "depends_on": ["schema"]},
        {"id": "loader", "files_create": ["engine/loader.py"], "depends_on": ["schema"]},
        {"id": "wiring", "files_modify": ["engine/executor.py"], "depends_on": ["models", "resolver", "loader"]},
    ]
    schedule = plan_dispatch(tasks)
    # schema first, then models+resolver+loader parallel, then wiring
    assert schedule.batches[0].task_ids == ["schema"]
    # Middle batch should be parallel
    middle = schedule.batches[1]
    assert middle.mode == "parallel"
    assert set(middle.task_ids) == {"models", "resolver", "loader"}
    # Last batch is wiring
    assert "wiring" in schedule.batches[-1].task_ids


def test_empty_tasks():
    schedule = plan_dispatch([])
    assert schedule.total_tasks == 0
    assert schedule.batches == []


def test_format_schedule():
    schedule = DispatchSchedule(batches=[])
    text = format_schedule(schedule)
    assert "0 tasks" in text


def test_single_task():
    tasks = [{"id": "only", "files_create": ["f.py"], "depends_on": []}]
    schedule = plan_dispatch(tasks)
    assert schedule.total_tasks == 1
    assert schedule.batches[0].mode == "sequential"


def test_conflicts_reported():
    tasks = [
        {"id": "t1", "files_modify": ["engine/shared.py"], "depends_on": []},
        {"id": "t2", "files_modify": ["engine/shared.py"], "depends_on": []},
    ]
    schedule = plan_dispatch(tasks)
    assert len(schedule.conflicts) >= 1
    assert schedule.conflicts[0]["severity"] == "high"
