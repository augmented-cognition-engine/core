# engine/graph/writer.py
"""Write task execution to the graph.

After task execution, writes:
  - agent_execution node (UPSERT by archetype+mode+perspective slug)
  - produced RELATE: agent_execution -> task (if completed)
  - improves RELATE: task -> graph_file (for each file touched)

Shadow graph_task / graph_agent tables are retired (Phase 3).
"""

from __future__ import annotations

import logging
import re

from core.engine.core.db import parse_one, parse_record_id, parse_rows, pool
from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _validate_graph_write_inputs(task_id: str, description: str, status: str) -> None:
    """Validate task graph write inputs before issuing DB queries.

    Raises ValidationError for empty task_id or description, and for unknown
    status values, which would silently write unusable nodes to the graph.
    """
    _VALID_STATUSES = frozenset(["completed", "failed", "cancelled", "running", "pending"])
    if not task_id or not task_id.strip():
        raise ValidationError("task_id must be non-empty")
    if not description or not description.strip():
        raise ValidationError("description must be non-empty")
    if status not in _VALID_STATUSES:
        raise ValidationError(f"Unknown status {status!r}. Valid: {sorted(_VALID_STATUSES)}")


def _slugify(text: str) -> str:
    """Convert arbitrary text to a safe SurrealDB record ID slug."""
    text = text.lower().strip()
    # Replace any non-alphanumeric chars (except hyphens/underscores) with underscores
    text = re.sub(r"[^a-z0-9_-]", "_", text)
    # Collapse multiple underscores
    text = re.sub(r"_+", "_", text)
    return text.strip("_") or "unknown"


def _agent_slug(classification: dict) -> str:
    """Derive a stable agent slug from classification config.

    E.g. practitioner_procedural_llm-engineering
    """
    archetype = _slugify(classification.get("archetype", "executor"))
    mode = _slugify(classification.get("mode", "reactive"))
    perspective = _slugify(classification.get("perspective", "practitioner"))
    parts = [perspective, mode, archetype]
    # Append first specialty if present to make slugs more specific
    specialties = classification.get("specialties", [])
    if specialties:
        parts.append(_slugify(str(specialties[0])))
    return "_".join(parts)


async def write_task_to_graph(
    task_id: str,
    description: str,
    status: str,
    output: str | None,
    feedback: str | None,
    classification: dict,
    files_touched: list[str] | None = None,
    graph_id: str = "default",
) -> dict:
    """Write a task execution to the graph.

    Creates:
    - agent_execution node (from classification)
    - produced RELATE: agent_execution -> task (if completed)
    - improves RELATE: task -> graph_file (for each file touched)

    Returns a summary dict with node IDs created.
    """
    _validate_graph_write_inputs(task_id, description, status)
    task_slug = _slugify(task_id.replace(":", "_"))
    agent_slug = _agent_slug(classification)

    archetype = classification.get("archetype", "executor")
    mode = classification.get("mode", "reactive")
    perspective = classification.get("perspective", "practitioner")
    specialties = classification.get("specialties", [])

    result: dict = {
        "task_rid": f"task:{task_slug}",
        "agent_rid": f"agent_execution:{agent_slug}",
        "edges": [],
    }

    async with pool.connection() as db:
        # 1. UPSERT agent_execution (WORK layer)
        ae_id = None
        ae_result = await db.query(
            """UPSERT type::record("agent_execution", <string>$slug) SET
                product = <record>$product,
                archetype = $archetype,
                mode = $mode,
                perspective = $perspective,
                specialties = $specialties,
                graph_id = $graph_id,
                created_at = time::now()""",
            {
                "slug": agent_slug,
                "product": "product:platform",
                "archetype": archetype,
                "mode": mode,
                "perspective": perspective,
                "specialties": specialties,
                "graph_id": graph_id,
            },
        )
        ae_row = parse_one(ae_result)
        if ae_row:
            ae_id = ae_row.get("id")

        # 2. RELATE: agent_execution -> produced -> task (if completed)
        if status == "completed" and output:
            if ae_id and task_id:
                await db.query(
                    """RELATE $ae -> produced -> $task SET
                        source = 'orchestrator', created_at = time::now()""",
                    {"ae": parse_record_id(ae_id), "task": parse_record_id(task_id)},
                )
                result["edges"].append("produced")

        # 3. RELATE: task -> improves -> graph_file (for each file touched)
        if files_touched:
            for file_path in files_touched:
                file_rows = await db.query(
                    "SELECT id FROM graph_file WHERE path = <string>$path AND graph_id = <string>$graph_id LIMIT 1",
                    {"path": file_path, "graph_id": graph_id},
                )
                rows = parse_rows(file_rows)
                if rows and rows[0].get("id"):
                    file_id = str(rows[0]["id"])
                    await db.query(
                        "RELATE $task -> improves -> $file SET source = 'orchestrator', created_at = time::now()",
                        {
                            "task": parse_record_id(task_id),
                            "file": parse_record_id(file_id),
                        },
                    )
                    result["edges"].append(f"improves:{file_path}")

    logger.debug(
        "Graph write: task=%s agent=%s edges=%s",
        result["task_rid"],
        result["agent_rid"],
        result["edges"],
    )
    return result
