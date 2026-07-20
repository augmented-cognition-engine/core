# engine/pm/tracker.py
"""Initiative lifecycle management and status tracking.

Handles create, activate, pause, cancel, complete.
Status roll-up from milestones → initiative.
Cost budget enforcement: warn at 80%, pause at 90%, require override at 100%.
Quick task mode: bypass initiative for simple/moderate complexity tasks.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_one, parse_rows
from core.engine.pm.initiative_states import InitiativeStateError
from core.engine.pm.initiative_states import transition as validate_initiative_transition

logger = logging.getLogger(__name__)

# Cost budget thresholds
COST_WARN_PCT = 0.80
COST_PAUSE_PCT = 0.90
COST_OVERRIDE_PCT = 1.00


def should_use_initiative(complexity: str) -> bool:
    """Determine if a task needs the initiative hierarchy.

    Simple/moderate → execute_task directly (quick task mode).
    Complex → create initiative with milestones and work items.
    """
    return complexity == "complex"


def compute_status_rollup(milestones: list[dict]) -> str:
    """Roll up milestone statuses to initiative status.

    Priority: blocked > review > active > pending > completed
    """
    if not milestones:
        return "pending"

    statuses = {ms.get("status", "pending") for ms in milestones}

    if "blocked" in statuses:
        return "blocked"
    if "review" in statuses:
        return "review"
    if "active" in statuses:
        return "active"
    if all(s == "completed" for s in statuses):
        return "completed"
    return "pending"


def compute_progress(milestones: list[dict]) -> float:
    """Compute progress percentage based on completed milestones."""
    if not milestones:
        return 0.0
    completed = sum(1 for ms in milestones if ms.get("status") == "completed")
    return round((completed / len(milestones)) * 100, 2)


def check_cost_budget(total_cost: float, budget: float | None) -> dict:
    """Check cost against budget thresholds.

    Returns: {"status": "ok"|"warn"|"pause"|"override_required", "percentage": float}
    """
    if budget is None or budget <= 0:
        return {"status": "ok", "percentage": 0.0}

    pct = total_cost / budget

    if pct >= COST_OVERRIDE_PCT:
        return {"status": "override_required", "percentage": round(pct * 100, 1)}
    elif pct >= COST_PAUSE_PCT:
        return {"status": "pause", "percentage": round(pct * 100, 1)}
    elif pct >= COST_WARN_PCT:
        return {"status": "warn", "percentage": round(pct * 100, 1)}
    return {"status": "ok", "percentage": round(pct * 100, 1)}


class InitiativeTracker:
    """Manage initiative lifecycle and track progress."""

    def __init__(self, db_pool=None):
        self._db_pool = db_pool

    def _pool(self):
        if self._db_pool:
            return self._db_pool
        from core.engine.core.db import pool

        return pool

    async def create_initiative(
        self,
        title: str,
        description: str,
        product_id: str,
        user_id: str,
        priority: str = "medium",
        cost_budget: float | None = None,
        git_base_branch: str | None = None,
        success_criteria: list[str] | None = None,
        source: str = "user_created",
        workspace_id: str | None = None,  # deprecated, ignored
    ) -> dict:
        """Create a new initiative in planning status."""
        async with self._pool().connection() as db:
            # SurrealDB v3: option<float> fields require NONE (not null/None) when absent
            cost_budget_sql = "$cost_budget" if cost_budget is not None else "NONE"
            params = {
                "product": product_id,
                "user": user_id,
                "title": title,
                "description": description,
                "source": source,
                "owner": user_id,
                "priority": priority,
                "cost_budget": cost_budget,
                "git_base_branch": git_base_branch or "main",
                "success_criteria": success_criteria or [],
            }
            result = await db.query(
                f"""
                CREATE initiative SET
                    product = <record>$product,
                    user = <record>$user,
                    title = $title,
                    description = $description,
                    status = 'planning',
                    source = $source,
                    owner = <record>$owner,
                    priority = $priority,
                    cost_budget = {cost_budget_sql},
                    git_base_branch = $git_base_branch,
                    success_criteria = $success_criteria
                """,
                params,
            )
            init = parse_one(result) or {"status": "planning", "title": title, "total_cost": 0.0}

            logger.info(
                "Created initiative: %s (%s)", title, init.get("id", "unknown") if isinstance(init, dict) else "unknown"
            )
            return init

    async def activate_initiative(self, initiative_id: str, product_id: str) -> dict:
        """Activate an initiative. Validates via the state machine.

        Accepts both 'ready' (normal path) and 'planning' (fast-track bypass)
        as valid source states for backward compatibility.
        """
        async with self._pool().connection() as db:
            result = await db.query(
                "SELECT * FROM <record>$id WHERE product = <record>$product",
                {"id": initiative_id, "product": product_id},
            )
            initiative = parse_one(result)
            if not initiative:
                return {"error": "Initiative not found"}

            current = initiative.get("status", "planning")
            # Fast-track: planning → active (bypass decomposing/ready for direct activation)
            if current == "planning":
                pass  # allow
            else:
                try:
                    validate_initiative_transition(current, "active")
                except InitiativeStateError:
                    return {"error": f"Cannot activate from state '{current}'"}

            await db.query(
                "UPDATE <record>$id SET status = 'active'",
                {"id": initiative_id},
            )
            return {**initiative, "status": "active"}

    async def pause_initiative(
        self,
        initiative_id: str,
        product_id: str,
    ) -> dict:
        """Pause a running initiative."""
        async with self._pool().connection() as db:
            await db.query(
                "UPDATE <record>$init_id SET status = 'paused'",
                {"init_id": initiative_id},
            )
            logger.info("Paused initiative %s", initiative_id)
            return {"id": initiative_id, "status": "paused"}

    async def cancel_initiative(
        self,
        initiative_id: str,
        product_id: str,
    ) -> dict:
        """Cancel an initiative. Cleans up active branches and releases locks."""
        async with self._pool().connection() as db:
            await db.query(
                "UPDATE <record>$init_id SET status = 'cancelled'",
                {"init_id": initiative_id},
            )

            # Release any locks held by this initiative's work items
            await db.query(
                """
                DELETE FROM resource_lock
                WHERE held_by CONTAINS $init_id
                """,
                {"init_id": initiative_id},
            )

            logger.info("Cancelled initiative %s", initiative_id)
            return {"id": initiative_id, "status": "cancelled"}

    async def complete_initiative(
        self,
        initiative_id: str,
        product_id: str,
    ) -> dict:
        """Complete an initiative when all milestones are done."""
        async with self._pool().connection() as db:
            await db.query(
                """
                UPDATE <record>$init_id SET
                    status = 'completed',
                    completed_at = time::now()
                """,
                {"init_id": initiative_id},
            )
            logger.info("Completed initiative %s", initiative_id)
            return {"id": initiative_id, "status": "completed"}

    async def get_initiative(
        self,
        initiative_id: str,
        product_id: str,
    ) -> dict | None:
        """Get initiative detail with milestones."""
        async with self._pool().connection() as db:
            result = await db.query(
                "SELECT * FROM <record>$init_id",
                {"init_id": initiative_id},
            )
            rows = parse_rows(result)
            if not rows:
                return None

            init = rows[0]

            # Load milestones
            ms_result = await db.query(
                """
                SELECT * FROM milestone
                WHERE initiative = $init_id AND product = <record>$product
                ORDER BY sequence ASC
                """,
                {"init_id": initiative_id, "product": product_id},
            )
            ms_rows = parse_rows(ms_result)

            init["milestones_detail"] = ms_rows
            init["progress"] = compute_progress(ms_rows)
            init["computed_status"] = compute_status_rollup(ms_rows)

            budget_check = check_cost_budget(
                init.get("total_cost", 0.0),
                init.get("cost_budget"),
            )
            init["budget_status"] = budget_check

            return init

    async def list_initiatives(
        self,
        product_id: str,
        status: str | None = None,
        project: str | None = None,
    ) -> list[dict]:
        """List initiatives with optional status and project filters."""
        project_clause = ""
        if project:
            # decision:6vacauzia2jc46hpvms8 — `= (SELECT VALUE ... LIMIT 1)` returns
            # empty in SurrealDB v3 (subquery yields 1-element array, not scalar).
            project_clause = " AND project IN (SELECT VALUE id FROM project WHERE product = <record>$product AND slug = <string>$project)"
        async with self._pool().connection() as db:
            if status:
                result = await db.query(
                    f"""
                    SELECT * FROM initiative
                    WHERE product = <record>$product AND status = $status{project_clause}
                    ORDER BY created_at DESC
                    """,
                    {"product": product_id, "status": status, "project": project},
                )
            else:
                result = await db.query(
                    f"""
                    SELECT * FROM initiative
                    WHERE product = <record>$product{project_clause}
                    ORDER BY created_at DESC
                    """,
                    {"product": product_id, "project": project},
                )
            return parse_rows(result)

    async def update_cost(
        self,
        initiative_id: str,
        cost_delta: float,
        product_id: str,
    ) -> dict:
        """Add cost to initiative total. Returns budget check result."""
        async with self._pool().connection() as db:
            await db.query(
                """
                UPDATE <record>$init_id SET
                    total_cost = total_cost + $delta
                """,
                {"init_id": initiative_id, "delta": cost_delta},
            )
            # Re-read for budget check
            result = await db.query(
                "SELECT total_cost, cost_budget FROM <record>$init_id",
                {"init_id": initiative_id},
            )
            rows = parse_rows(result)
            init = rows[0] if rows else {}

            budget_check = check_cost_budget(
                init.get("total_cost", 0.0),
                init.get("cost_budget"),
            )
            return budget_check
