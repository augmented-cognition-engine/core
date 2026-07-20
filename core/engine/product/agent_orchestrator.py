# engine/product/agent_orchestrator.py
"""Agent Orchestrator — manage cross-agent execution of decomposition plans.

Executes work units from a DecompositionPlan respecting dependencies:
- Parallel batches get worktree isolation + airspace monitoring
- Sequential batches get context threading from predecessor outputs
- Handles blocker feedback (pause downstream, trigger replan)
- Tracks overall progress

ATC model: graph assigns airspace, worktrees isolate, monitor enforces.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class UnitStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class UnitContext:
    """Structured context from a completed predecessor unit."""

    unit_id: str
    title: str
    output_summary: str
    files_changed: list[str]
    status: str


class AgentOrchestrator:
    """Manage cross-agent execution of decomposition plans."""

    def __init__(self, db_pool, airspace_assigner=None, on_progress=None):
        self._pool = db_pool
        self._unit_status: dict[str, UnitStatus] = {}
        self._unit_results: dict[str, dict] = {}
        self._airspace = airspace_assigner
        self._airspace_map: dict = {}
        # Optional async callback fired after each batch: on_progress(progress_dict)
        self._on_progress = on_progress

    async def execute_plan(self, plan_dict: dict, product_id: str) -> dict:
        """Execute a decomposition plan batch by batch.

        plan_dict has: spec_id, units, batches, conflicts

        For each batch:
        1. Start all units in the batch
        2. Wait for completion
        3. Check results — if any blocked, pause downstream
        4. Move to next batch

        Idempotent: if the spec is already executing or verifying (e.g. duplicate
        conductor dispatch), returns the current status without re-running units.

        Returns execution summary.
        """
        spec_id = plan_dict.get("spec_id", "")
        units = {u["id"]: u for u in plan_dict.get("units", [])}
        batches = plan_dict.get("batches", [])

        # Idempotency guard — prevent duplicate concurrent executions of the same spec.
        # The conductor may dispatch the same spec twice if an event fires twice; the
        # spec's DB status is the authoritative lock.
        if spec_id and self._pool:
            try:
                from core.engine.core.db import parse_one

                async with self._pool.connection() as db:
                    spec_row = parse_one(
                        await db.query(
                            "SELECT status FROM ONLY <record>$id LIMIT 1",
                            {"id": spec_id},
                        )
                    )
                current_status = spec_row.get("status", "") if spec_row else ""
                if current_status in ("executing", "verifying"):
                    logger.info(
                        "execute_plan skipped — spec %s already %s (idempotency guard)",
                        spec_id,
                        current_status,
                    )
                    return {
                        "spec_id": spec_id,
                        "skipped": True,
                        "reason": f"already {current_status}",
                        "total_units": len(units),
                        "completed": 0,
                        "failed": 0,
                        "blocked": 0,
                    }
            except Exception as exc:
                logger.warning("Idempotency check failed (proceeding): %s", exc)

        # Initialize all units as pending
        for uid in units:
            self._unit_status[uid] = UnitStatus.PENDING

        # Compute airspace assignments if assigner available
        self._airspace_map: dict = {}
        if self._airspace:
            try:
                self._airspace_map = await self._airspace.assign(list(units.values()), product_id)
                if self._airspace_map:
                    logger.info("ATC airspace assigned for %d units", len(self._airspace_map))
            except Exception as exc:
                logger.warning("Airspace assignment failed (proceeding without): %s", exc)

        completed = 0
        failed = 0
        blocked = 0

        for batch_idx, batch in enumerate(batches):
            batch_ids = batch.get("task_ids", [])
            mode = batch.get("mode", "sequential")

            logger.info(f"Batch {batch_idx + 1}/{len(batches)}: {len(batch_ids)} units ({mode})")

            # Check if any units in this batch are blocked by failed predecessors
            runnable = []
            for uid in batch_ids:
                unit = units.get(uid, {})
                deps = unit.get("depends_on", [])
                if any(self._unit_status.get(d) == UnitStatus.FAILED for d in deps):
                    self._unit_status[uid] = UnitStatus.BLOCKED
                    blocked += 1
                    logger.warning(f"Unit {uid} blocked — dependency failed")
                elif any(self._unit_status.get(d) == UnitStatus.BLOCKED for d in deps):
                    self._unit_status[uid] = UnitStatus.BLOCKED
                    blocked += 1
                else:
                    runnable.append(uid)

            if not runnable:
                continue

            if mode == "parallel":
                # Parallel: agents share the same workspace.
                # ATC airspace assignment prevents file overlap — no per-agent
                # worktrees needed.  Initiative-level worktrees (if any) are
                # managed by the flight registry / session runner, not here.
                results = await asyncio.gather(
                    *[self._execute_unit(uid, units[uid], product_id) for uid in runnable],
                    return_exceptions=True,
                )
                for uid, result in zip(runnable, results):
                    if isinstance(result, Exception):
                        self._unit_status[uid] = UnitStatus.FAILED
                        self._unit_results[uid] = {"error": str(result)}
                        failed += 1
                    else:
                        self._unit_status[uid] = UnitStatus.COMPLETED
                        self._unit_results[uid] = result
                        completed += 1
            else:
                # Sequential with context threading
                for uid in runnable:
                    prior = self._build_prior_context(uid, units[uid])
                    try:
                        result = await self._execute_unit(
                            uid,
                            units[uid],
                            product_id,
                            prior_context=prior,
                        )
                        self._unit_status[uid] = UnitStatus.COMPLETED
                        self._unit_results[uid] = result
                        completed += 1
                    except Exception as e:
                        self._unit_status[uid] = UnitStatus.FAILED
                        self._unit_results[uid] = {"error": str(e)}
                        failed += 1

            # Fire progress callback after each batch (non-blocking, non-fatal)
            if self._on_progress:
                try:
                    await self._on_progress(self.get_progress())
                except Exception as exc:
                    logger.debug("on_progress callback failed (non-fatal): %s", exc)

        # Persist execution summary
        summary = {
            "spec_id": spec_id,
            "total_units": len(units),
            "completed": completed,
            "failed": failed,
            "blocked": blocked,
            "unit_status": {uid: s.value for uid, s in self._unit_status.items()},
        }

        # Update spec status based on results
        if completed == len(units):
            new_status = "verifying"
        elif failed > 0:
            new_status = "failed"
        else:
            new_status = "executing"

        try:
            async with self._pool.connection() as db:
                await db.query(
                    "UPDATE <record>$spec_id SET status = $status, updated_at = time::now()",
                    {"spec_id": spec_id, "status": new_status},
                )
                try:
                    from core.engine.events.bus import bus

                    await bus.emit(
                        "spec.execution_complete",
                        {
                            "product_id": product_id,
                            "spec_id": spec_id,
                            "completed": completed,
                            "failed": failed,
                            "blocked": blocked,
                            "status": new_status,
                        },
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to update spec status: {e}")

        summary["spec_status"] = new_status
        return summary

    async def _execute_unit(
        self,
        unit_id: str,
        unit: dict,
        product_id: str,
        prior_context: list[UnitContext] | None = None,
    ) -> dict:
        """Execute a single work unit via the orchestrator executor."""
        self._unit_status[unit_id] = UnitStatus.RUNNING
        title = unit.get("title", "Untitled")
        archetype = unit.get("archetype", "creator")
        description = unit.get("description", title)
        logger.info(f"Executing unit {unit_id}: {title} (archetype: {archetype})")

        try:
            from core.engine.orchestrator.executor import execute_task

            # Build description with context from the work unit
            files = unit.get("files_create", []) + unit.get("files_modify", [])
            full_description = description
            if files:
                full_description += f"\n\nFiles to work with: {', '.join(files)}"

            # Inject prior context from completed predecessors
            if prior_context:
                full_description += "\n\n" + _format_prior_context(prior_context)

            # Inject ATC airspace scope
            airspace = self._airspace_map.get(unit_id)
            if airspace and airspace.owned_files:
                full_description += (
                    f"\n\n## Your File Scope (ATC)\n"
                    f"You are authorized to modify: {', '.join(sorted(airspace.owned_files))}"
                )
                if airspace.boundary_files:
                    full_description += (
                        f"\nReference only (do not modify): {', '.join(sorted(airspace.boundary_files))}"
                    )

            result = await execute_task(
                description=full_description,
                product_id=product_id,
                workspace_id="workspace:default",
                user_id="user:system",
            )

            return {
                "unit_id": unit_id,
                "status": "completed",
                "title": title,
                "task_id": result.get("id"),
                "output": result.get("output", ""),
            }
        except Exception as e:
            logger.error(f"Unit {unit_id} execution failed: {e}")
            raise

    def _build_prior_context(self, unit_id: str, unit: dict) -> list[UnitContext] | None:
        """Build structured context from completed predecessor units.

        Reads depends_on to find predecessors, then pulls their outputs
        from self._unit_results.
        """
        deps = unit.get("depends_on", [])
        if not deps:
            return None

        contexts = []
        for dep_id in deps:
            if self._unit_status.get(dep_id) != UnitStatus.COMPLETED:
                continue
            result = self._unit_results.get(dep_id, {})
            contexts.append(
                UnitContext(
                    unit_id=dep_id,
                    title=result.get("title", dep_id),
                    output_summary=_truncate(result.get("output", ""), 500),
                    files_changed=result.get("files_changed", []),
                    status="completed",
                )
            )

        return contexts if contexts else None

    def get_progress(self) -> dict:
        """Get current execution progress."""
        total = len(self._unit_status)
        if total == 0:
            return {"total": 0, "completed": 0, "pct": 0}
        completed = sum(1 for s in self._unit_status.values() if s == UnitStatus.COMPLETED)
        return {
            "total": total,
            "completed": completed,
            "running": sum(1 for s in self._unit_status.values() if s == UnitStatus.RUNNING),
            "blocked": sum(1 for s in self._unit_status.values() if s == UnitStatus.BLOCKED),
            "failed": sum(1 for s in self._unit_status.values() if s == UnitStatus.FAILED),
            "pct": int(completed / total * 100),
        }


def _format_prior_context(contexts: list[UnitContext]) -> str:
    """Format prior unit contexts into a prompt section."""
    lines = ["## Prior Work (from completed predecessor units)"]
    for ctx in contexts:
        lines.append(f"\n### {ctx.unit_id}: {ctx.title} [{ctx.status}]")
        if ctx.output_summary:
            lines.append(f"Output: {ctx.output_summary}")
        if ctx.files_changed:
            lines.append(f"Files changed: {', '.join(ctx.files_changed)}")
    return "\n".join(lines)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
