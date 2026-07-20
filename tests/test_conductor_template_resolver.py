# tests/test_conductor_template_resolver.py
"""Tests for quality template resolution (layered inheritance)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.conductor.template_resolver import DEFAULT_THRESHOLDS, TemplateResolver


def _make_pool(db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


def _make_db(*side_effects):
    effects = list(side_effects)

    async def _query(*_a, **_kw):
        return effects.pop(0) if effects else []

    db = AsyncMock()
    db.query = AsyncMock(side_effect=_query)
    return db


@pytest.mark.asyncio
async def test_resolve_returns_universal_default_when_no_templates():
    db = _make_db([], [], [], [])  # 4 queries, all empty
    resolver = TemplateResolver(_make_pool(db))
    cap = {"tags": [], "project": None}
    result = await resolver.resolve(cap, "testing", "product:test")
    assert result["threshold"] == DEFAULT_THRESHOLDS["testing"]
    assert result["scope"] == "universal_default"


@pytest.mark.asyncio
async def test_resolve_org_template_wins_over_universal_default():
    org_tmpl = [{"threshold": 0.7, "stretch_target": 0.9, "weight": 1.5, "checklist": None, "scope": "org"}]
    db = _make_db([], [], org_tmpl, [])  # cap_type empty, project empty, org hit, universal skip
    resolver = TemplateResolver(_make_pool(db))
    cap = {"tags": ["api"], "project": None}
    result = await resolver.resolve(cap, "security", "product:test")
    assert result["threshold"] == 0.7
    assert result["weight"] == 1.5


@pytest.mark.asyncio
async def test_resolve_capability_type_wins_over_org():
    cap_tmpl = [
        {"threshold": 0.8, "stretch_target": 0.95, "weight": 2.0, "checklist": None, "scope": "capability_type"}
    ]
    db = _make_db(cap_tmpl)  # First query matches, short-circuit
    resolver = TemplateResolver(_make_pool(db))
    cap = {"tags": ["auth"], "project": None}
    result = await resolver.resolve(cap, "security", "product:test")
    assert result["threshold"] == 0.8


def test_default_thresholds_exist_for_all_key_dimensions():
    assert "security" in DEFAULT_THRESHOLDS
    assert "testing" in DEFAULT_THRESHOLDS
    assert DEFAULT_THRESHOLDS["security"] == 0.6
    assert DEFAULT_THRESHOLDS["testing"] == 0.5
