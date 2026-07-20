# engine/api/graph_events.py
"""Graph event API — structured graph updates from the ACE capture hook.

The capture hook (scripts/ace_capture_hook.py) fires on every tool call
and POSTs structured events here instead of flat text observations.
Each event type maps to graph node/edge operations in SurrealDB.
"""

import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, pool, serialize_record

logger = logging.getLogger(__name__)

router = APIRouter(tags=["graph-events"])

# ---------------------------------------------------------------------------
# Valid event types
# ---------------------------------------------------------------------------

EventType = Literal[
    "file_modified",
    "file_created",
    "file_read",
    "test_run",
    "commit",
]


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class GraphEventRequest(BaseModel):
    type: EventType
    file_path: str | None = None  # path relative to repo root or absolute
    context: str | None = None  # human-readable description of the change
    session_id: str | None = None
    graph_id: str = "default"

    # For test_run: source files covered by the test file
    source_files: list[str] | None = None

    # For commit: commit message / SHA
    commit_message: str | None = None
    commit_sha: str | None = None

    @field_validator("file_path")
    @classmethod
    def strip_file_path(cls, v: str | None) -> str | None:
        return v.strip() if v else v

    @field_validator("context")
    @classmethod
    def truncate_context(cls, v: str | None) -> str | None:
        if v and len(v) > 2000:
            return v[:2000]
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_path_to_slug(path: str) -> str:
    """Convert a file path to a safe SurrealDB record ID component.

    e.g. "engine/core/db.py" → "engine_core_db_py"
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", path)
    slug = slug.strip("_").lower()
    return slug or "unknown"


async def _upsert_graph_file(db, path: str, graph_id: str, access_only: bool = False) -> str:
    """Create or update a graph_file node. Returns the record ID string."""
    slug = _file_path_to_slug(path)
    record_id = f"graph_file:{slug}"

    if access_only:
        # Only increment access counter — lightweight
        await db.query(
            """
            UPSERT type::record("graph_file", <string>$slug) MERGE {
                path: $path,
                name: $name,
                graph_id: $graph_id,
                last_accessed: time::now(),
                access_count: IF access_count THEN access_count + 1 ELSE 1 END
            }
            """,
            {
                "slug": slug,
                "path": path,
                "name": path.split("/")[-1],
                "graph_id": graph_id,
            },
        )
    else:
        # Full upsert — touched by edit/write
        await db.query(
            """
            UPSERT type::record("graph_file", <string>$slug) MERGE {
                path: $path,
                name: $name,
                graph_id: $graph_id,
                last_modified: time::now(),
                last_accessed: time::now(),
                change_frequency: IF change_frequency THEN change_frequency + 1 ELSE 1 END,
                access_count: IF access_count THEN access_count + 1 ELSE 1 END
            }
            """,
            {
                "slug": slug,
                "path": path,
                "name": path.split("/")[-1],
                "graph_id": graph_id,
            },
        )

    return record_id


async def _create_decision_node(
    db,
    graph_id: str,
    title: str,
    rationale: str | None,
    session_id: str | None,
) -> str | None:
    """Create a graph_decision node. Returns the record ID string or None on failure."""
    try:
        result = await db.query(
            """
            CREATE graph_decision SET
                graph_id = $graph_id,
                title = $title,
                rationale = $rationale,
                session_id = $session_id,
                created_at = time::now()
            """,
            {
                "graph_id": graph_id,
                "title": title[:500] if title else "Untitled decision",
                "rationale": rationale or "",
                "session_id": session_id or "",
            },
        )
        row = parse_one(result)
        if row:
            return str(serialize_record(row.get("id", "")))
    except Exception as exc:
        logger.debug("Failed to create decision node: %s", exc)
    return None


async def _create_edge(db, from_id: str, edge_type: str, to_id: str, graph_id: str) -> None:
    """Create a RELATE edge between two graph nodes."""
    try:
        await db.query(
            f"RELATE $from->{edge_type}->$to SET graph_id = $graph_id",
            {
                "from": from_id,
                "to": to_id,
                "graph_id": graph_id,
            },
        )
    except Exception as exc:
        logger.debug("Failed to create edge %s -[%s]-> %s: %s", from_id, edge_type, to_id, exc)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


async def _handle_file_modified(db, body: GraphEventRequest) -> dict:
    """file_modified → update graph_file + create decision + improves edge."""
    if not body.file_path:
        raise HTTPException(status_code=422, detail="file_path required for file_modified")

    file_id = await _upsert_graph_file(db, body.file_path, body.graph_id)

    decision_id = None
    if body.context:
        decision_id = await _create_decision_node(
            db,
            graph_id=body.graph_id,
            title=f"Modified {body.file_path.split('/')[-1]}",
            rationale=body.context,
            session_id=body.session_id,
        )
        if decision_id:
            # decision improves the file it changed
            await _create_edge(db, decision_id, "improves", file_id, body.graph_id)

    return {
        "status": "ok",
        "event": "file_modified",
        "file_id": file_id,
        "decision_id": decision_id,
    }


async def _handle_file_created(db, body: GraphEventRequest) -> dict:
    """file_created → create graph_file + decision + produced edge."""
    if not body.file_path:
        raise HTTPException(status_code=422, detail="file_path required for file_created")

    file_id = await _upsert_graph_file(db, body.file_path, body.graph_id)

    decision_id = None
    if body.context:
        decision_id = await _create_decision_node(
            db,
            graph_id=body.graph_id,
            title=f"Created {body.file_path.split('/')[-1]}",
            rationale=body.context,
            session_id=body.session_id,
        )
        if decision_id:
            # decision produced the new file
            await _create_edge(db, decision_id, "produced", file_id, body.graph_id)

    return {
        "status": "ok",
        "event": "file_created",
        "file_id": file_id,
        "decision_id": decision_id,
    }


async def _handle_file_read(db, body: GraphEventRequest) -> dict:
    """file_read → increment access_count on graph_file."""
    if not body.file_path:
        raise HTTPException(status_code=422, detail="file_path required for file_read")

    file_id = await _upsert_graph_file(db, body.file_path, body.graph_id, access_only=True)

    return {
        "status": "ok",
        "event": "file_read",
        "file_id": file_id,
    }


async def _handle_test_run(db, body: GraphEventRequest) -> dict:
    """test_run → create tests edges between test file and source files."""
    if not body.file_path:
        raise HTTPException(status_code=422, detail="file_path (test file) required for test_run")

    test_file_id = await _upsert_graph_file(db, body.file_path, body.graph_id, access_only=True)

    edge_count = 0
    for src_path in body.source_files or []:
        if src_path.strip():
            src_id = await _upsert_graph_file(db, src_path.strip(), body.graph_id, access_only=True)
            await _create_edge(db, test_file_id, "tests", src_id, body.graph_id)
            edge_count += 1

    return {
        "status": "ok",
        "event": "test_run",
        "test_file_id": test_file_id,
        "edges_created": edge_count,
    }


async def _handle_commit(db, body: GraphEventRequest) -> dict:
    """commit → create graph_decision node from commit message."""
    if not body.commit_message:
        raise HTTPException(status_code=422, detail="commit_message required for commit event")

    title = body.commit_message.splitlines()[0][:500]
    decision_id = await _create_decision_node(
        db,
        graph_id=body.graph_id,
        title=title,
        rationale=body.commit_message,
        session_id=body.session_id,
    )

    return {
        "status": "ok",
        "event": "commit",
        "decision_id": decision_id,
        "commit_sha": body.commit_sha or "",
    }


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_HANDLERS = {
    "file_modified": _handle_file_modified,
    "file_created": _handle_file_created,
    "file_read": _handle_file_read,
    "test_run": _handle_test_run,
    "commit": _handle_commit,
}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/graph/event", status_code=200)
async def record_graph_event(
    body: GraphEventRequest,
    user: dict = Depends(get_current_user),
):
    """Record a structured graph event from the capture hook.

    Each event type maps to specific graph node/edge operations:
    - file_modified: update graph_file + create decision + improves edge
    - file_created:  create graph_file + decision + produced edge
    - file_read:     increment access_count on graph_file
    - test_run:      create tests edges between test file and source files
    - commit:        create graph_decision from commit message
    """
    handler = _HANDLERS.get(body.type)
    if not handler:
        raise HTTPException(status_code=422, detail=f"Unknown event type: {body.type}")

    try:
        async with pool.connection() as db:
            return await handler(db, body)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("graph_event handler failed for type=%s: %s", body.type, exc)
        raise HTTPException(status_code=500, detail="Graph event processing failed")
