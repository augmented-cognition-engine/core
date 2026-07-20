"""Unit tests for the pure helpers that compute the four BriefingPayload
fields that previously shipped as stubs.

These helpers receive their inputs as plain values; no DB. The integration
test (test_substrate_acceptance.py) covers the wired-up behavior.
"""

from __future__ import annotations

import pytest


def test_target_drift_assessment_none_when_no_demo_target():
    from core.engine.sentinel.engines.briefing import compute_target_drift_assessment

    out = compute_target_drift_assessment(
        demo_target=None,
        pattern_to_pillar={},
        pillar_scores={},
        phase_floors={},
    )
    assert out is None


def test_target_drift_assessment_zero_blocked_when_all_clear():
    from core.engine.product.ambition import DemoTarget
    from core.engine.sentinel.engines.briefing import compute_target_drift_assessment

    dt = DemoTarget(name="d", target_date="2026-12-31", required_patterns=["a", "b"])
    out = compute_target_drift_assessment(
        demo_target=dt,
        pattern_to_pillar={"a": "experience", "b": "operations"},
        pillar_scores={"experience": 0.8, "operations": 0.5},
        phase_floors={"experience": 0.7, "operations": 0.35},
    )
    assert out is not None
    assert out.n_total == 2
    assert out.n_blocked == 0
    assert out.blocking_pillars == []


def test_target_drift_assessment_lists_blocking_pillars():
    from core.engine.product.ambition import DemoTarget
    from core.engine.sentinel.engines.briefing import compute_target_drift_assessment

    dt = DemoTarget(name="d", target_date="2026-12-31", required_patterns=["a", "b", "c"])
    out = compute_target_drift_assessment(
        demo_target=dt,
        pattern_to_pillar={"a": "experience", "b": "experience", "c": "trust"},
        pillar_scores={"experience": 0.3, "trust": 0.5},
        phase_floors={"experience": 0.7, "trust": 0.7},
    )
    assert out.n_total == 3
    assert out.n_blocked == 3
    assert sorted(out.blocking_pillars) == ["experience", "trust"]


def test_compute_discipline_breakdown_groups_by_pillar():
    from core.engine.sentinel.engines.briefing import compute_discipline_breakdown

    dim_scores = {"aix": 0.4, "ux": 0.6, "observability": 0.7, "deployment": 0.5}
    breakdown = compute_discipline_breakdown(dim_scores)
    assert "experience" in breakdown
    assert "operations" in breakdown
    assert breakdown["experience"]["aix"] == pytest.approx(0.4, abs=0.001)
    assert breakdown["operations"]["observability"] == pytest.approx(0.7, abs=0.001)


def test_compute_discipline_breakdown_skips_unknown_dims():
    from core.engine.sentinel.engines.briefing import compute_discipline_breakdown

    breakdown = compute_discipline_breakdown({"unknown_dim": 0.5, "aix": 0.4})
    assert "aix" in breakdown.get("experience", {})
    # unknown_dim should not appear in any pillar
    for pillar_dims in breakdown.values():
        assert "unknown_dim" not in pillar_dims


def test_compute_sensor_coverage_keys_are_canonical():
    from core.engine.sentinel.engines.briefing import compute_sensor_coverage

    coverage = compute_sensor_coverage(disciplines_with_recent_data=set())
    expected_keys = {
        "experience.aix",
        "experience.content_design.voice_consistency",
        "experience.aix.demo_readiness",
        "evolution.engineering_culture.contributor_coordination",
    }
    assert set(coverage.keys()) == expected_keys
    # All False when no data
    assert all(v is False for v in coverage.values())


def test_compute_sensor_coverage_true_for_disciplines_with_data():
    from core.engine.sentinel.engines.briefing import compute_sensor_coverage

    coverage = compute_sensor_coverage(disciplines_with_recent_data={"aix"})
    assert coverage["experience.aix"] is True
    assert coverage["experience.aix.demo_readiness"] is True
    # Different discipline — still False
    assert coverage["evolution.engineering_culture.contributor_coordination"] is False
    assert coverage["experience.content_design.voice_consistency"] is False
