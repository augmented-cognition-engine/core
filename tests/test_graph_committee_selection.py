"""Graph-informed committee selection — the membership-side of Graph Tensions.

When the task's discipline has a live tension (breaks/reverts/causes) with another discipline in the
graph, that other lens is convened so the committee deliberates the contradiction. Pure helpers tested
here; the DB-backed graph_tension_lenses is fail-open. See
docs/superpowers/specs/2026-06-23-graph-informed-committee-selection-design.md.
"""

from __future__ import annotations

from core.engine.orchestration.composition_scorer import _discipline_of, inject_tension_lenses


def test_discipline_of_extracts_token():
    assert _discipline_of("technology.security.appsec") == "security"
    assert _discipline_of("technology.performance") == "performance"
    assert _discipline_of("security") == "security"


def test_discipline_of_handles_empty_and_garbage():
    assert _discipline_of("") is None
    assert _discipline_of(None) is None
    assert _discipline_of("technology") == "technology"  # single token → itself


def test_inject_adds_new_tension_lens():
    out = inject_tension_lenses(["security"], ["performance"], "security", max_lenses=5)
    assert out == ["security", "performance"]


def test_inject_dedups_existing_lens():
    out = inject_tension_lenses(["security", "performance"], ["performance"], "security", max_lenses=5)
    assert out == ["security", "performance"]  # no duplicate, order stable


def test_inject_keeps_primary_first_and_respects_cap():
    # cap=2: primary + one tension lens; extras dropped, primary never dropped.
    out = inject_tension_lenses(["security", "architecture"], ["performance", "data"], "security", max_lenses=2)
    assert out[0] == "security"
    assert len(out) == 2


def test_inject_never_drops_primary_even_when_full():
    out = inject_tension_lenses(["architecture", "data"], ["performance"], "security", max_lenses=2)
    assert "security" in out  # primary forced in
    assert out[0] == "security"
    assert len(out) == 2


def test_inject_empty_tension_lenses_is_noop():
    base = ["security", "architecture"]
    assert inject_tension_lenses(base, [], "security", max_lenses=5) == base


def test_inject_tension_survives_when_committee_full():
    # The committee is already at cap with learned lenses; a live tension lens must STILL get in
    # (high-signal contradiction — the case the feature exists for). Guaranteed a slot after primary.
    out = inject_tension_lenses(["security", "a", "b", "c"], ["performance"], "security", max_lenses=4)
    assert out[0] == "security"
    assert "performance" in out, "a live tension lens must survive even when the committee is full"
    assert len(out) == 4


# ── graph_tension_lenses (DB-backed; live-verified to fire — these lock logic + fail-open) ──────

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402


def _edge_pool(edges_by_type):
    pool = MagicMock()
    conn = MagicMock()

    async def q(query, params=None):
        for et in ("breaks", "reverts", "causes"):
            if f"FROM {et}" in query:
                return [edges_by_type.get(et, [])]
        return [[]]

    conn.query = q
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.mark.asyncio
async def test_graph_tension_lenses_returns_other_side(monkeypatch):
    """For a `testing` task, the disciplines on the OTHER side of its tension/consequence edges convene."""
    import core.engine.orchestration.composition_scorer as cs

    edges = {
        "breaks": [{"a": "testing", "b": "dependency_management", "ap": "testing", "bp": "dependency_management"}],
        "causes": [{"a": "observability", "b": "testing", "ap": "observability", "bp": "testing"}],
    }
    with patch.object(cs, "pool", _edge_pool(edges)):
        out = await cs.graph_tension_lenses({"discipline": "testing", "specialties": []}, "product:test", cap=5)
    assert out == ["dependency_management", "observability"]  # the other side of each edge; primary excluded


@pytest.mark.asyncio
async def test_graph_tension_lenses_excludes_primary_and_caps(monkeypatch):
    import core.engine.orchestration.composition_scorer as cs

    edges = {
        "breaks": [
            {"a": "testing", "b": "testing", "ap": "testing", "bp": "testing"},  # self-tension → excluded
            {"a": "testing", "b": "security", "ap": "testing", "bp": "security"},
            {"a": "testing", "b": "performance", "ap": "testing", "bp": "performance"},
        ]
    }
    with patch.object(cs, "pool", _edge_pool(edges)):
        out = await cs.graph_tension_lenses({"discipline": "testing"}, "product:test", cap=1)
    assert out == ["security"]  # self excluded; capped at 1


@pytest.mark.asyncio
async def test_graph_tension_lenses_fail_open(monkeypatch):
    """Any DB error → [] (committee unchanged), never raises."""
    import core.engine.orchestration.composition_scorer as cs

    boom = MagicMock()
    boom.connection.side_effect = RuntimeError("graph down")
    with patch.object(cs, "pool", boom):
        out = await cs.graph_tension_lenses({"discipline": "testing"}, "product:test")
    assert out == []
