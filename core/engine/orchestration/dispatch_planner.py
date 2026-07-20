# engine/orchestration/dispatch_planner.py
"""Plan task dispatch planner — determines parallel vs sequential execution.

Uses predict_merge_conflicts from the PM git module to analyze file overlap
between plan tasks. Produces a dispatch schedule that tells the orchestrator
which tasks can run in parallel (with worktrees) and which must be sequential.

Usage:
    from core.engine.orchestration.dispatch_planner import plan_dispatch

    tasks = [
        {"id": "task-1", "files_create": ["engine/foo.py"], "files_modify": [], "depends_on": []},
        {"id": "task-2", "files_create": ["engine/bar.py"], "files_modify": [], "depends_on": []},
        {"id": "task-3", "files_create": [], "files_modify": ["engine/foo.py"], "depends_on": ["task-1"]},
    ]
    schedule = plan_dispatch(tasks)
    # schedule.batches = [
    #   {"tasks": ["task-1", "task-2"], "mode": "parallel"},
    #   {"tasks": ["task-3"], "mode": "sequential"},
    # ]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.engine.pm.git import predict_merge_conflicts

logger = logging.getLogger(__name__)


@dataclass
class DispatchBatch:
    """A batch of tasks to execute together."""

    task_ids: list[str]
    mode: str  # "parallel" | "sequential"
    reason: str = ""


@dataclass
class DispatchSchedule:
    """Ordered sequence of batches — execute top to bottom."""

    batches: list[DispatchBatch] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)

    @property
    def total_tasks(self) -> int:
        return sum(len(b.task_ids) for b in self.batches)

    @property
    def parallel_batches(self) -> int:
        return sum(1 for b in self.batches if b.mode == "parallel")


def _validate_tasks(tasks: list[dict]) -> None:
    """Validate a task list before dispatch planning.

    Raises ValueError if any task is missing an 'id', or if 'depends_on'
    references a task_id that doesn't exist in the list.  Empty lists are
    valid and produce an empty schedule.
    """
    if not tasks:
        return
    all_ids = {t.get("id") for t in tasks if t.get("id")}
    for task in tasks:
        if not task.get("id"):
            raise ValueError(f"Every task must have an 'id' field; got {task!r}")
        for dep in task.get("depends_on", []):
            if dep not in all_ids:
                raise ValueError(f"Task {task['id']!r} depends on unknown task {dep!r}")


def _extract_files(task: dict) -> set[str]:
    """Extract all files a task touches (create + modify + test)."""
    files = set()
    for key in ("files_create", "files_modify", "files_test"):
        for f in task.get(key, []):
            if isinstance(f, str):
                # Strip line number references like "engine/foo.py:123-145"
                files.add(f.split(":")[0])
    return files


def _build_dependency_graph(tasks: list[dict]) -> dict[str, set[str]]:
    """Build task_id → set of task_ids it depends on."""
    deps: dict[str, set[str]] = {}
    for task in tasks:
        task_id = task["id"]
        deps[task_id] = set(task.get("depends_on", []))
    return deps


def plan_dispatch(tasks: list[dict]) -> DispatchSchedule:
    """Analyze plan tasks and produce an execution schedule.

    Raises ValueError if tasks contains invalid task dicts
    (see _validate_tasks for invariants).  An empty list returns an empty schedule.

    Each task dict should have:
        id: str — unique task identifier
        files_create: list[str] — files this task creates
        files_modify: list[str] — files this task modifies
        files_test: list[str] — test files this task creates/runs
        depends_on: list[str] — task IDs this task depends on

    Returns a DispatchSchedule with ordered batches.
    """
    _validate_tasks(tasks)

    logger.debug("Planning dispatch for %d tasks", len(tasks))

    # Build file maps for conflict prediction
    task_file_map = {}
    for task in tasks:
        task_id = task["id"]
        task_file_map[task_id] = _extract_files(task)

    # Build dependency graph
    deps = _build_dependency_graph(tasks)
    task_by_id = {t["id"]: t for t in tasks}

    # Predict file conflicts
    conflict_items = [{"id": tid, "files_touched": sorted(files)} for tid, files in task_file_map.items()]
    conflicts = predict_merge_conflicts(conflict_items)

    # Build conflict adjacency (which tasks conflict with each other)
    conflict_pairs: set[tuple[str, str]] = set()
    for c in conflicts:
        if c.get("severity") == "high":
            pair = (c["item_a"], c["item_b"])
            conflict_pairs.add(pair)
            conflict_pairs.add((pair[1], pair[0]))

    # Topological sort with parallelism detection
    schedule = DispatchSchedule(conflicts=conflicts)
    completed: set[str] = set()
    remaining = set(task_by_id.keys())

    while remaining:
        # Find tasks whose dependencies are all completed
        ready = []
        for tid in remaining:
            if deps[tid].issubset(completed):
                ready.append(tid)

        if not ready:
            # Circular dependency — force sequential
            logger.warning("Circular dependency detected, forcing sequential: %s", remaining)
            for tid in sorted(remaining):
                schedule.batches.append(
                    DispatchBatch(
                        task_ids=[tid],
                        mode="sequential",
                        reason="circular dependency fallback",
                    )
                )
            break

        # Partition ready tasks into parallel-safe groups
        # Tasks that conflict with each other must not be in the same parallel batch
        parallel_group: list[str] = []
        sequential_overflow: list[str] = []

        for tid in ready:
            # Check if this task conflicts with any already in the parallel group
            has_conflict = any((tid, other) in conflict_pairs for other in parallel_group)
            if has_conflict:
                sequential_overflow.append(tid)
            else:
                parallel_group.append(tid)

        # Emit parallel batch (if 2+ tasks, use worktrees)
        if len(parallel_group) >= 2:
            schedule.batches.append(
                DispatchBatch(
                    task_ids=parallel_group,
                    mode="parallel",
                    reason=f"{len(parallel_group)} tasks with no file overlap",
                )
            )
        elif parallel_group:
            schedule.batches.append(
                DispatchBatch(
                    task_ids=parallel_group,
                    mode="sequential",
                    reason="single ready task",
                )
            )

        # Emit sequential tasks that conflicted
        for tid in sequential_overflow:
            schedule.batches.append(
                DispatchBatch(
                    task_ids=[tid],
                    mode="sequential",
                    reason="file conflict with parallel batch",
                )
            )

        completed.update(ready)
        remaining -= set(ready)

    logger.debug(
        "Dispatch plan complete: %d batches, %d parallel, %d conflicts",
        len(schedule.batches),
        schedule.parallel_batches,
        len(schedule.conflicts),
    )
    return schedule


def format_schedule(schedule: DispatchSchedule) -> str:
    """Format a dispatch schedule for display."""
    lines = [f"Dispatch Schedule ({schedule.total_tasks} tasks, {schedule.parallel_batches} parallel batches)"]
    if schedule.conflicts:
        lines.append(f"  Conflicts detected: {len(schedule.conflicts)}")
    lines.append("")

    for i, batch in enumerate(schedule.batches, 1):
        mode_icon = "⟂" if batch.mode == "parallel" else "→"
        task_list = ", ".join(batch.task_ids)
        lines.append(f"  Batch {i} {mode_icon} [{batch.mode}] {task_list}")
        if batch.reason:
            lines.append(f"    {batch.reason}")

    return "\n".join(lines)
