# tests/test_intelligence_schema.py
"""Tests for the intelligence SurrealDB schema module."""


def test_schema_importable():
    from core.engine.intelligence.schema import SCHEMA_STATEMENTS, apply_schema

    assert len(SCHEMA_STATEMENTS) >= 3
    assert callable(apply_schema)


def test_schema_statements_are_strings():
    from core.engine.intelligence.schema import SCHEMA_STATEMENTS

    for stmt in SCHEMA_STATEMENTS:
        assert isinstance(stmt, str)
        assert len(stmt) > 0


def test_schema_covers_required_tables():
    from core.engine.intelligence.schema import SCHEMA_STATEMENTS

    combined = " ".join(SCHEMA_STATEMENTS)
    assert "code_symbol" in combined
    assert "code_analysis" in combined
    assert "calls" in combined
