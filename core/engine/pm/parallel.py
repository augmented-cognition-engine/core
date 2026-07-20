# engine/pm/parallel.py
"""Parallel work item execution with conflict prediction gates.

Groups work items by parallel_group, runs non-conflicting items via
asyncio.gather, falls back to sequential when files overlap.
Concurrency caps: max_parallel_work_items=3, max_parallel_tasks=5, max_llm_calls=10.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Callable

from core.engine.orchestration.agent import AgentConfig
from core.engine.orchestrator.archetypes import ARCHETYPE_INSTRUCTIONS, MODE_INSTRUCTIONS
from core.engine.pm.git import predict_merge_conflicts

logger = logging.getLogger(__name__)

# Concurrency caps from Doc 22
DEFAULT_MAX_PARALLEL_WORK_ITEMS = 3
DEFAULT_MAX_PARALLEL_TASKS = 5
DEFAULT_MAX_LLM_CALLS = 10

# Default post-task hooks
DEFAULT_POST_TASK_HOOKS = ["type-check", "lint", "unit-test", "format"]


async def run_post_task_hooks(
    hooks: list[str],
    run_hook_fn: Callable | None = None,
    work_dir: str | None = None,
) -> list[dict]:
    """Run post-task hooks sequentially. Each hook is a validation step.

    Hooks run in order: type-check → lint → unit-test → format.
    Returns list of results. Failures don't block subsequent hooks.
    """
    results = []
    for hook_name in hooks:
        try:
            if run_hook_fn:
                result = await run_hook_fn(hook_name, work_dir=work_dir)
            else:
                result = await _default_run_hook(hook_name, work_dir)
            results.append(result)
        except Exception as e:
            logger.warning("Post-task hook '%s' failed: %s", hook_name, e)
            results.append({"hook": hook_name, "passed": False, "error": str(e)})
    return results


async def _default_run_hook(hook_name: str, work_dir: str | None = None) -> dict:
    """Default hook runner — placeholder for actual tool invocations."""
    logger.info("Running post-task hook: %s", hook_name)
    return {"hook": hook_name, "passed": True}


# Severity ordering — also in git.py, imported for local use
_SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1, "none": 0}


def wi_to_agent_config(wi: dict) -> AgentConfig:
    """Convert a work item dict to an AgentConfig for the Team pattern."""
    archetype = wi.get("archetype", "executor")
    mode = wi.get("mode", "reactive")

    archetype_instruction = ARCHETYPE_INSTRUCTIONS.get(archetype, ARCHETYPE_INSTRUCTIONS["executor"])
    mode_instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["reactive"])
    description = wi.get("description", wi.get("title", ""))

    system_prompt = f"{archetype_instruction}\n{mode_instruction}\n\nYour task: {description}"

    return AgentConfig(
        role=wi.get("title", "worker"),
        system_prompt=system_prompt,
        metadata={
            "work_item_id": wi.get("id", ""),
            "files_touched": wi.get("files_touched", []),
            "domain_path": wi.get("domain_path", ""),
            "archetype": archetype,
            "mode": mode,
        },
    )


def build_milestone_task(work_items: list[dict], milestone_context: dict) -> str:
    """Build the orchestration task description from milestone context."""
    title = milestone_context.get("title", "Milestone")
    description = milestone_context.get("description", "")

    wi_summaries = []
    for wi in work_items:
        files = ", ".join(wi.get("files_touched", [])[:5]) or "unspecified"
        wi_summaries.append(f"- **{wi.get('title', 'Work Item')}** ({wi.get('domain_path', '')}): files [{files}]")

    return f"## {title}\n{description}\n\n### Work Items in This Group\n" + "\n".join(wi_summaries)


def max_severity(conflicts: list[dict]) -> str:
    """Return the highest severity across all conflicts."""
    if not conflicts:
        return "none"
    return max(
        conflicts,
        key=lambda c: _SEVERITY_ORDER.get(c.get("severity", "none"), 0),
    ).get("severity", "none")


def map_results_to_work_items(orch_result, work_items: list[dict]) -> list[dict]:
    """Map OrchestrationResult back to per-WI result dicts."""
    if orch_result.pattern_result is None or orch_result.status != "completed":
        error = orch_result.error or "Orchestration failed"
        return [{"id": wi.get("id", ""), "output": "", "status": "failed", "error": error} for wi in work_items]

    agent_results = orch_result.pattern_result.agent_results
    results = []

    for i, wi in enumerate(work_items):
        if i < len(agent_results):
            ar = agent_results[i]
            results.append(
                {
                    "id": wi.get("id", ""),
                    "output": ar.output,
                    "status": ar.status,
                    "error": ar.error,
                }
            )
        else:
            results.append(
                {
                    "id": wi.get("id", ""),
                    "output": "",
                    "status": "failed",
                    "error": "No agent result for this work item",
                }
            )

    return results


class ParallelExecutor:
    """Execute work items in parallel groups with conflict prediction gates.

    For groups with 2+ items and no high-severity conflicts, elevates to a
    single Team pattern orchestration run for cross-agent DISCOVERY forwarding.
    """

    def __init__(
        self,
        product_id: str = "product:default",
        workspace_id: str = "workspace:default",
        user_id: str = "user:system",
        max_parallel_work_items: int = DEFAULT_MAX_PARALLEL_WORK_ITEMS,
        max_parallel_tasks: int = DEFAULT_MAX_PARALLEL_TASKS,
        max_llm_calls: int = DEFAULT_MAX_LLM_CALLS,
    ):
        self.product_id = product_id
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.max_parallel_work_items = max_parallel_work_items
        self.max_parallel_tasks = max_parallel_tasks
        self.max_llm_calls = max_llm_calls
        self._semaphore = asyncio.Semaphore(max_parallel_work_items)

    async def _execute_single_work_item(self, wi: dict, product_id: str) -> dict:
        """Execute a single work item. Override in production to call real executor."""
        raise NotImplementedError("Must be overridden or monkey-patched")

    async def _execute_sequential(
        self,
        work_items: list[dict],
        product_id: str,
    ) -> list[dict]:
        """Execute work items sequentially (conflict fallback)."""
        results = []
        for wi in work_items:
            result = await self._execute_single_work_item(wi, product_id)
            results.append(result)
        return results

    async def execute_parallel_group(
        self,
        work_items: list[dict],
        product_id: str,
    ) -> list[dict]:
        """Execute a parallel group of work items.

        Single WI -> direct execution.
        High severity conflicts -> sequential fallback.
        Otherwise -> Team pattern orchestration run.
        """
        if len(work_items) == 0:
            return []

        if len(work_items) == 1:
            result = await self._execute_single_work_item(work_items[0], product_id)
            return [result]

        # Check conflicts for pattern selection
        conflicts = predict_merge_conflicts(work_items)
        severity = max_severity(conflicts)

        if severity == "high":
            logger.info(
                "High severity conflicts — sequential fallback (%d conflicts)",
                len(conflicts),
            )
            return await self._execute_sequential(work_items, product_id)

        # Elevate to Team pattern orchestration run
        logger.info("Elevating %d work items to Team pattern", len(work_items))

        agent_configs = [wi_to_agent_config(wi) for wi in work_items]

        from core.engine.orchestration import orchestrate
        from core.engine.orchestration.request import OrchestrationRequest

        milestone_context = {
            "title": "Parallel Work Group",
            "description": f"{len(work_items)} work items executing concurrently",
        }

        request = OrchestrationRequest(
            description=build_milestone_task(work_items, milestone_context),
            product_id=product_id,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            source="runner",
            pattern="team",
            agent_configs=agent_configs,
            persist_task=True,
            run_post_hooks=True,
        )

        result = await orchestrate(request)

        return map_results_to_work_items(result, work_items)

    async def execute_milestone_work_items(
        self,
        work_items: list[dict],
        product_id: str,
    ) -> list[dict]:
        """Execute all work items in a milestone, grouped by parallel_group."""
        groups: dict[int, list[dict]] = defaultdict(list)
        for wi in work_items:
            pg = wi.get("parallel_group") or 0
            groups[pg].append(wi)

        all_results = []
        for group_id in sorted(groups.keys()):
            group = groups[group_id]
            logger.info("Executing parallel group %d (%d work items)", group_id, len(group))
            results = await self.execute_parallel_group(group, product_id)
            all_results.extend(results)

        return all_results
