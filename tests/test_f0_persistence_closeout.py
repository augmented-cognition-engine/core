from pathlib import Path

import pytest

from core.engine.graph.assertions import _query_or_raise


@pytest.mark.asyncio
async def test_assertion_writes_fail_closed_on_surreal_string_errors():
    class DB:
        async def query(self, query, params):
            return "schema validation failed"

    with pytest.raises(RuntimeError, match="schema validation failed"):
        await _query_or_raise(DB(), "UPSERT relationship_assertion:test", {})


def test_v142_uses_surreal_v3_flexible_and_relation_endpoint_syntax():
    schema = (Path(__file__).parents[1] / "core/schema/v142_relational_assertions.surql").read_text()
    assert "FLEXIBLE TYPE" not in schema
    assert "TYPE object FLEXIBLE" in schema
    assert "DEFINE FIELD in ON assertion_dependency" not in schema
    assert "DEFINE FIELD out ON assertion_dependency" not in schema


def test_closeout_verifier_is_disposable_and_checks_both_schema_paths():
    script = (Path(__file__).parents[1] / "scripts/verify_f0_persistence.py").read_text()
    assert 'tempfile.mkdtemp(prefix="ace-f0-closeout-", dir="/tmp")' in script
    assert "through=141" in script
    assert "through=142" in script
    assert "fresh_upgrade_byte_identical" in script
    assert "api_restart_byte_identical" in script
