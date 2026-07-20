# tests/test_intelligence_export_pack.py
"""Tests for ace_export_pack — portable prompt pack export.

Produces a single markdown bundle capturing the product's learned intelligence
for a given discipline. The key property: output is a valid, LLM-readable
document that can be prepended to any agent's context.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_export_pack_contains_expected_sections():
    from core.engine.intelligence.export_pack import export_prompt_pack

    async def fake_query(sql, params=None):
        if "FROM insight" in sql:
            return [
                [
                    {"content": "always use get_llm()", "confidence": 0.9, "tier": "specialty"},
                    {"content": "SurrealDB v3 requires <record> casts", "confidence": 0.95, "tier": "subdomain"},
                ]
            ]
        if "FROM decision" in sql:
            return [[{"title": "Use Postgres", "rationale": "ACID", "alternatives": ["MongoDB"]}]]
        if "FROM star_trace" in sql:
            return [[{"task_description": "refactor auth", "final_output": "done", "confidence": 0.88}]]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    md = await export_prompt_pack(mock_db, product_id="product:test", discipline="architecture")

    assert "# ACE Intelligence Pack" in md
    assert "architecture" in md.lower()
    assert "always use get_llm()" in md
    assert "SurrealDB v3" in md
    assert "Use Postgres" in md
    assert "refactor auth" in md


@pytest.mark.asyncio
async def test_export_pack_noop_on_no_data():
    """No data → valid (minimal) document, not an error."""
    from core.engine.intelligence.export_pack import export_prompt_pack

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    md = await export_prompt_pack(mock_db, product_id="product:test", discipline="architecture")
    assert "# ACE Intelligence Pack" in md
    assert "No insights" in md or "no data" in md.lower()


@pytest.mark.asyncio
async def test_export_pack_limits_by_top_n():
    """Must respect the `limit` cap to keep pack size predictable."""
    from core.engine.intelligence.export_pack import export_prompt_pack

    many = [{"content": f"insight {i}", "confidence": 0.9, "tier": "specialty"} for i in range(200)]

    async def fake_query(sql, params=None):
        if "FROM insight" in sql:
            return [many]
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    md = await export_prompt_pack(mock_db, product_id="product:test", discipline="testing", limit=10)
    count = md.count("insight ")  # loose count — each insight line references "insight <N>"
    assert count <= 20  # header + some formatting tolerance; won't exceed a small multiple


@pytest.mark.asyncio
async def test_export_pack_includes_metadata_header():
    """Pack must include generated_at and product metadata for auditability."""
    from core.engine.intelligence.export_pack import export_prompt_pack

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    md = await export_prompt_pack(mock_db, product_id="product:platform", discipline="security")
    assert "product:platform" in md
    assert "security" in md.lower()
    assert "Generated:" in md or "generated_at" in md.lower()


@pytest.mark.asyncio
async def test_export_pack_db_failure_degrades_gracefully():
    """A partial DB failure returns a valid pack with a warning section."""
    from core.engine.intelligence.export_pack import export_prompt_pack

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("db gone"))

    md = await export_prompt_pack(mock_db, product_id="product:test", discipline="architecture")
    # Must not raise; at minimum an error-graceful header
    assert "# ACE Intelligence Pack" in md
