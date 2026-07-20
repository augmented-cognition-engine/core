"""ace_forget MCP tool: dry-run by default, erases on confirm."""

import pytest

from core.engine.capture.atomic_write import atomic_capture_write
from core.engine.core.db import parse_one
from core.engine.mcp.tools import ace_forget

_TEST_PRODUCT = "product:test_aceforget_55503"


@pytest.fixture(autouse=True)
async def _cleanup(db_pool):
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE insight WHERE product = <record>$p", {"p": _TEST_PRODUCT})
        await db.query("DELETE forget_log WHERE product = <record>$p", {"p": _TEST_PRODUCT})


@pytest.mark.asyncio
async def test_ace_forget_dry_run_then_confirm(db_pool):
    iid = await atomic_capture_write(
        db_pool,
        insight_fields={
            "product": _TEST_PRODUCT,
            "content": "ace-forget-tool-unique-55503",
            "insight_type": "fact",
            "tier": "domain",
            "clearance": "open",
            "confidence": 0.9,
            "source_domain": "test",
            "domain_path": "test",
            "domain": None,
            "subdomain": None,
            "specialty": None,
            "tags": [],
        },
        embedding=None,
        specialty_slug=None,
        observation_ids=[],
    )
    preview = await ace_forget(iid, reason="test", actor="tester", product_id=_TEST_PRODUCT)
    assert preview.get("would_erase") is True
    async with db_pool.connection() as db:
        assert parse_one(await db.query("SELECT id FROM <record>$id", {"id": iid})) is not None

    done = await ace_forget(
        iid,
        reason="test",
        actor="tester",
        confirm=True,
        product_id=_TEST_PRODUCT,
    )
    assert done.get("erased") is True
    async with db_pool.connection() as db:
        assert parse_one(await db.query("SELECT id FROM <record>$id", {"id": iid})) is None
