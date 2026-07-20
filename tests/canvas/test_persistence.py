# tests/canvas/test_persistence.py
import pytest

from core.engine.canvas.models import ParticipantKind, ShapeKind
from core.engine.canvas.persistence import (
    append_event,
    create_session,
    get_session,
    list_artifacts,
    upsert_artifact,
)
from core.engine.core.db import parse_rows, pool

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_create_and_get_session(db_pool):
    s = await create_session(project_id="p1", title="Postgres or Dynamo?", created_by="user:edwin")
    assert s.id.startswith("canvas_session:")
    fetched = await get_session(s.id)
    assert fetched.title == "Postgres or Dynamo?"


@pytest.mark.asyncio
async def test_upsert_artifact_round_trip(db_pool):
    s = await create_session(project_id="p1", title="t")
    # First upsert — creates
    a1 = await upsert_artifact(
        session_id=s.id,
        shape_kind=ShapeKind.STICKY,
        tldraw_shape_id="shape:abc",
        payload={"text": "Postgres or Dynamo?"},
        x=100,
        y=200,
        author=ParticipantKind.HUMAN,
    )
    # Second upsert same tldraw_shape_id — updates, must not create a second row
    a2 = await upsert_artifact(
        session_id=s.id,
        shape_kind=ShapeKind.STICKY,
        tldraw_shape_id="shape:abc",
        payload={"text": "Updated text"},
        x=110,
        y=210,
        author=ParticipantKind.HUMAN,
    )
    arts = await list_artifacts(s.id)
    matching = [a for a in arts if a.tldraw_shape_id == "shape:abc"]
    assert len(matching) == 1, "upsert must not create duplicate rows for the same tldraw_shape_id"
    assert matching[0].payload == {"text": "Updated text"}


@pytest.mark.asyncio
async def test_upsert_artifact_lists_both_when_different_shapes(db_pool):
    s = await create_session(project_id="p1", title="t")
    await upsert_artifact(
        session_id=s.id,
        shape_kind=ShapeKind.STICKY,
        tldraw_shape_id="shape:first",
        payload={},
        x=0,
        y=0,
        author=ParticipantKind.HUMAN,
    )
    await upsert_artifact(
        session_id=s.id,
        shape_kind=ShapeKind.STICKY,
        tldraw_shape_id="shape:second",
        payload={},
        x=1,
        y=1,
        author=ParticipantKind.HUMAN,
    )
    arts = await list_artifacts(s.id)
    shape_ids = {a.tldraw_shape_id for a in arts}
    assert {"shape:first", "shape:second"} <= shape_ids


@pytest.mark.asyncio
async def test_append_event_log_orders_chronologically(db_pool):
    s = await create_session(project_id="p1", title="t")
    await append_event(session_id=s.id, event_type="session.opened", payload={}, surface="canvas")
    await append_event(
        session_id=s.id,
        event_type="artifact.placed",
        payload={"shape_kind": "sticky"},
        surface="canvas",
    )
    # Per feedback_surrealdb_orderby_select.md: ORDER BY field MUST appear in SELECT.
    async with pool.connection() as db:
        result = await db.query(
            f"SELECT event_type, created_at FROM canvas_event WHERE session_id = {s.id} ORDER BY created_at;"
        )
    types = [r["event_type"] for r in parse_rows(result)]
    assert types == ["session.opened", "artifact.placed"]
