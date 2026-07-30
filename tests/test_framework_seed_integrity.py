from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.cognition.seed import NEW_FRAMEWORKS, ensure_frameworks_seeded, seed_frameworks


def test_v158_repairs_framework_schema_for_nested_seed_objects():
    schema = (Path(__file__).parents[1] / "core" / "schema" / "v158_framework_nested_objects.surql").read_text()

    assert "DEFINE TABLE IF NOT EXISTS framework SCHEMAFULL" in schema
    for field in ("archetype_affinity", "mode_affinity", "composability"):
        assert f"DEFINE FIELD OVERWRITE {field}" in schema
        definition = next(line for line in schema.splitlines() if f"OVERWRITE {field}" in line)
        assert "ON framework TYPE object FLEXIBLE" in definition


def test_framework_seed_library_has_177_unique_authored_prompts():
    assert len(NEW_FRAMEWORKS) == 177
    assert len({fw["slug"] for fw in NEW_FRAMEWORKS}) == 177
    assert all(str(fw.get("system_prompt", "")).strip() for fw in NEW_FRAMEWORKS)


def test_api_startup_verifies_framework_prompt_library():
    source = (Path(__file__).parents[1] / "core" / "engine" / "api" / "main.py").read_text()
    assert "framework_count = await ensure_frameworks_seeded()" in source
    assert "ACE cannot start without its built-in framework prompt library" in source


def test_api_startup_fails_closed_on_schema_migration_error():
    source = (Path(__file__).parents[1] / "core" / "engine" / "api" / "main.py").read_text()
    assert "ACE cannot start with unapplied schema migrations" in source
    assert "Schema migration failed (non-fatal)" not in source


def test_worker_startup_verifies_complete_framework_prompt_library():
    source = (Path(__file__).parents[1] / "core" / "engine" / "worker" / "app.py").read_text()
    assert "framework_count = await ensure_frameworks_seeded()" in source
    assert "ACE worker cannot start without its built-in framework prompt library" in source
    assert "SELECT count() AS n FROM framework" not in source


def test_v159_aligns_runner_schema_with_product_scoped_runtime():
    root = Path(__file__).parents[1]
    schema = (root / "core" / "schema" / "v159_runner_product_scope.surql").read_text()
    enqueue = (root / "core" / "engine" / "api" / "runner.py").read_text()

    assert "product ON runner_config TYPE option<record<product>>" in schema
    assert "product ON task_queue TYPE option<record<product>>" in schema
    assert "'recommendation'" in schema
    assert "metadata ON task_queue TYPE option<object> FLEXIBLE" in schema
    assert "CREATE task_queue SET\n                product = <record>$product" in enqueue


def test_v160_makes_self_optimizer_payloads_flexible_and_product_scoped():
    root = Path(__file__).parents[1]
    schema = (root / "core" / "schema" / "v160_self_optimizer_objects.surql").read_text()
    producer = (root / "core" / "engine" / "sentinel" / "engines" / "self_optimizer.py").read_text()

    assert "draft\n    ON self_optimizer_proposal TYPE option<object> FLEXIBLE" in schema
    assert "evidence\n    ON self_optimizer_proposal TYPE object FLEXIBLE DEFAULT {}" in schema
    assert "ON self_optimizer_proposal FIELDS product, status, type" in schema
    assert "CREATE self_optimizer_proposal SET\n                    product = <record>$product" in producer
    assert "type = $type" in producer
    assert "name = $name" in producer


@pytest.mark.asyncio
async def test_ensure_frameworks_seeds_and_verifies_missing_library():
    expected_rows = [{"slug": fw["slug"], "system_prompt": fw["system_prompt"]} for fw in NEW_FRAMEWORKS]

    with (
        patch(
            "core.engine.cognition.seed.parse_rows",
            side_effect=[[], expected_rows],
        ),
        patch("core.engine.cognition.seed.pool") as mock_pool,
        patch(
            "core.engine.cognition.seed.seed_frameworks",
            new_callable=AsyncMock,
            return_value=(177, 0),
        ) as mock_seed,
    ):
        mock_db = AsyncMock()
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_db
        mock_context.__aexit__.return_value = False
        mock_pool.connection.return_value = mock_context

        count = await ensure_frameworks_seeded()

    assert count == 177
    mock_seed.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_frameworks_raises_when_sdk_returns_write_error_string():
    with patch("core.engine.cognition.seed.pool") as mock_pool:
        mock_db = AsyncMock()
        mock_db.query.side_effect = [[], "nested object rejected"] * len(NEW_FRAMEWORKS)
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_db
        mock_context.__aexit__.return_value = False
        mock_pool.connection.return_value = mock_context

        with pytest.raises(RuntimeError, match="177 write"):
            await seed_frameworks()
