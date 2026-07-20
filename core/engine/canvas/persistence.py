# engine/canvas/persistence.py
"""SurrealDB CRUD for canvas tables.

Follows ACE conventions: parse_rows()/parse_one() for round-trips.
SCHEMALESS tables — writes use SET form with explicit <datetime> casts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from core.engine.canvas.models import CanvasArtifact, CanvasSession, ParticipantKind, ShapeKind
from core.engine.core.db import parse_one, parse_rows, pool

logger = logging.getLogger(__name__)


def _slug() -> str:
    return uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_session(
    project_id: str,
    title: str,
    created_by: Optional[str] = None,
) -> CanvasSession:
    sid = f"canvas_session:{_slug()}"
    now = _now()
    async with pool.connection() as db:
        result = await db.query(
            f"""
            CREATE {sid} SET
                project_id = $project_id,
                title = $title,
                created_at = <datetime>$now,
                updated_at = <datetime>$now,
                created_by = $created_by;
            """,
            {"project_id": project_id, "title": title, "now": now, "created_by": created_by},
        )
    row = parse_one(result)
    if row is None:
        raise RuntimeError(f"create_session failed for project={project_id!r}, title={title!r}")
    return CanvasSession(**row)


async def get_session(session_id: str) -> CanvasSession:
    async with pool.connection() as db:
        result = await db.query(f"SELECT * FROM {session_id};")
    row = parse_one(result)
    if row is None:
        raise ValueError(f"canvas_session {session_id!r} not found")
    return CanvasSession(**row)


async def patch_session(session_id: str, title: str) -> CanvasSession:
    now = _now()
    async with pool.connection() as db:
        result = await db.query(
            f"UPDATE {session_id} SET title = $title, updated_at = <datetime>$now;",
            {"title": title, "now": now},
        )
    row = parse_one(result)
    if row is None:
        raise ValueError(f"canvas_session {session_id!r} not found")
    return CanvasSession(**row)


async def list_sessions(project_id: str | None = None, limit: int = 20) -> list[CanvasSession]:
    clause = "WHERE project_id = $project_id" if project_id else ""
    bindings: dict[str, Any] = {"limit": limit}
    if project_id:
        bindings["project_id"] = project_id
    async with pool.connection() as db:
        result = await db.query(
            f"SELECT * FROM canvas_session {clause} ORDER BY created_at DESC LIMIT $limit;",
            bindings,
        )
    rows = parse_rows(result)
    sessions = []
    for r in rows:
        r.setdefault("title", "Untitled")
        try:
            sessions.append(CanvasSession(**r))
        except Exception:
            pass
    return sessions


async def upsert_artifact(
    session_id: str,
    shape_kind: ShapeKind,
    tldraw_shape_id: str,
    payload: dict[str, Any],
    x: float,
    y: float,
    author: ParticipantKind,
) -> CanvasArtifact:
    now = _now()
    bindings: dict[str, Any] = {
        "session_id": session_id,
        "shape_kind": shape_kind.value,
        "tldraw_shape_id": tldraw_shape_id,
        "payload": payload,
        "x": x,
        "y": y,
        "author": author.value,
        "now": now,
    }
    # SELECT first to decide CREATE vs UPDATE.
    async with pool.connection() as db:
        existing = await db.query(
            "SELECT * FROM canvas_artifact "
            "WHERE session_id = <record>$session_id "
            "AND tldraw_shape_id = $tldraw_shape_id LIMIT 1;",
            {"session_id": session_id, "tldraw_shape_id": tldraw_shape_id},
        )
    existing_row = parse_one(existing)

    async with pool.connection() as db:
        if existing_row:
            aid = str(existing_row["id"])
            result = await db.query(
                f"""
                UPDATE {aid} SET
                    shape_kind = $shape_kind,
                    payload = $payload,
                    x = $x, y = $y,
                    author = $author,
                    updated_at = <datetime>$now;
                """,
                bindings,
            )
        else:
            aid = f"canvas_artifact:{_slug()}"
            result = await db.query(
                f"""
                CREATE {aid} SET
                    session_id = <record>$session_id,
                    shape_kind = $shape_kind,
                    tldraw_shape_id = $tldraw_shape_id,
                    payload = $payload,
                    x = $x, y = $y,
                    author = $author,
                    created_at = <datetime>$now,
                    updated_at = <datetime>$now;
                """,
                bindings,
            )
    row = parse_one(result)
    if row is None:
        raise RuntimeError(f"upsert_artifact failed for session={session_id!r}, shape={tldraw_shape_id!r}")

    # Metabolism trigger: an UPDATE to an existing artifact may have shifted the
    # ground under beliefs that ground in it — enqueue them for re-evaluation. A
    # CREATE has nothing grounded in it yet, so it is not a trigger. Best-effort:
    # the artifact write is the source of truth and must never fail on the metabolism.
    if existing_row is not None:
        try:
            from core.engine.graph.metabolism import enqueue_reeval_for_object

            await enqueue_reeval_for_object(aid)
        except Exception:
            logger.warning("metabolism enqueue failed for %s", aid, exc_info=True)

    return CanvasArtifact(**row)


async def list_artifacts(session_id: str) -> list[CanvasArtifact]:
    async with pool.connection() as db:
        # SELECT * includes created_at so ORDER BY created_at satisfies v3 rule.
        result = await db.query(
            "SELECT * FROM canvas_artifact WHERE session_id = <record>$session_id ORDER BY created_at;",
            {"session_id": session_id},
        )
    return [CanvasArtifact(**r) for r in parse_rows(result)]


async def append_event(
    session_id: str,
    event_type: str,
    payload: dict[str, Any],
    surface: str = "canvas",
) -> None:
    eid = f"canvas_event:{_slug()}"
    now = _now()
    async with pool.connection() as db:
        result = await db.query(
            f"""
            CREATE {eid} SET
                session_id = <record>$session_id,
                event_type = $event_type,
                payload = $payload,
                surface = $surface,
                created_at = <datetime>$now;
            """,
            {"session_id": session_id, "event_type": event_type, "payload": payload, "surface": surface, "now": now},
        )
    # append_event returns None but we still validate the write didn't fail.
    if parse_one(result) is None:
        raise RuntimeError(f"append_event failed for session={session_id!r}, event_type={event_type!r}")
