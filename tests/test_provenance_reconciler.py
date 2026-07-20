import pytest

from core.engine.core.db import parse_one
from core.engine.sentinel.engines.provenance_reconciler import reconcile_missing_provenance

_TEST_PRODUCT = "product:test_provenance_44120"


@pytest.fixture(autouse=True)
async def _cleanup(db_pool):
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE insight WHERE product = <record>$p", {"p": _TEST_PRODUCT})


async def _make(db_pool, source_domain: str) -> str:
    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                "CREATE ONLY insight SET product = <record>$p, content = $c, insight_type = 'fact', "
                "tier = 'domain', source_domain = $sd, confidence = 0.7, tags = [], status = 'active', "
                "created_at = time::now(), updated_at = time::now(), last_confirmed = time::now() RETURN id",
                {"p": _TEST_PRODUCT, "c": "prov-" + source_domain, "sd": source_domain},
            )
        )
    return str(row["id"])


@pytest.mark.asyncio
async def test_reconciler_populates_provenance(db_pool):
    iid = await _make(db_pool, "sentinel.domain_research")
    async with db_pool.connection() as db:
        pre = parse_one(await db.query("SELECT trust FROM <record>$id", {"id": iid}))
    assert pre.get("trust") is None

    n = await reconcile_missing_provenance(limit=500)
    assert n >= 1

    async with db_pool.connection() as db:
        row = parse_one(await db.query("SELECT source_kind, source_ref, trust FROM <record>$id", {"id": iid}))
    assert row["source_kind"] == "sentinel"
    assert row["source_ref"] == "domain_research"
    assert row["trust"] == 0.65


@pytest.mark.asyncio
async def test_reconciler_idempotent(db_pool):
    iid = await _make(db_pool, "architecture")
    await reconcile_missing_provenance(limit=500)
    async with db_pool.connection() as db:
        row = parse_one(await db.query("SELECT source_kind, trust FROM <record>$id", {"id": iid}))
    assert row["source_kind"] == "capture" and row["trust"] == 0.80
    n2 = await reconcile_missing_provenance(limit=500)
    async with db_pool.connection() as db:
        still = parse_one(await db.query("SELECT trust FROM <record>$id", {"id": iid}))
    assert still["trust"] == 0.80
