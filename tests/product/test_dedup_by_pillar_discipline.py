"""Sentinel test for the pillar/discipline dedup in StrategicPrioritizer.

Without dedup, the briefing's top_recommendations renders multiple lines per
(pillar, discipline) — once per capability below floor. Pure-function test
verifies the dedup picks the worst-gap representative per group.
"""

from core.engine.product.strategic_prioritizer import _dedup_by_pillar_discipline


def test_dedup_collapses_same_pillar_discipline_keeping_worst_gap():
    enriched = [
        {"pillar": "experience", "discipline": "accessibility", "gap": 0.3, "rank": 0.5},
        {"pillar": "experience", "discipline": "accessibility", "gap": 0.5, "rank": 0.7},
        {"pillar": "experience", "discipline": "accessibility", "gap": 0.4, "rank": 0.6},
    ]
    result = _dedup_by_pillar_discipline(enriched)
    assert len(result) == 1
    assert result[0]["gap"] == 0.5  # worst-gap representative


def test_dedup_preserves_distinct_pillar_discipline_pairs():
    enriched = [
        {"pillar": "experience", "discipline": "accessibility", "gap": 0.3, "rank": 0.5},
        {"pillar": "experience", "discipline": "ux", "gap": 0.2, "rank": 0.4},
        {"pillar": "operations", "discipline": "observability", "gap": 0.1, "rank": 0.3},
    ]
    result = _dedup_by_pillar_discipline(enriched)
    assert len(result) == 3
    keys = {(r["pillar"], r["discipline"]) for r in result}
    assert keys == {
        ("experience", "accessibility"),
        ("experience", "ux"),
        ("operations", "observability"),
    }


def test_dedup_treats_none_discipline_as_distinct_from_string():
    enriched = [
        {"pillar": "state", "discipline": None, "gap": 0.4, "rank": 0.5},
        {"pillar": "state", "discipline": "data_modeling", "gap": 0.3, "rank": 0.4},
    ]
    result = _dedup_by_pillar_discipline(enriched)
    assert len(result) == 2


def test_dedup_empty_input_returns_empty():
    assert _dedup_by_pillar_discipline([]) == []


def test_dedup_keeps_rank_field_intact():
    """The full row is preserved — dedup picks among rows, doesn't transform them."""
    enriched = [
        {
            "pillar": "experience",
            "discipline": "ux",
            "gap": 0.3,
            "rank": 0.5,
            "rationale": "lower",
            "blocking_patterns": ["a"],
        },
        {
            "pillar": "experience",
            "discipline": "ux",
            "gap": 0.5,
            "rank": 0.7,
            "rationale": "winner",
            "blocking_patterns": ["b"],
        },
    ]
    result = _dedup_by_pillar_discipline(enriched)
    assert len(result) == 1
    assert result[0]["rationale"] == "winner"
    assert result[0]["blocking_patterns"] == ["b"]
    assert result[0]["rank"] == 0.7
