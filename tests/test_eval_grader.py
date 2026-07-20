"""Tests for the eval grader — baseline-relative regression gate (item B).

The grader is pure logic: results + committed baseline -> verdict. It absorbs single-case LLM
variance (tolerance) while failing on genuine regressions and on any case that flipped pass->fail
vs the baseline (newly_broken). See docs/superpowers/specs/2026-06-22-eval-harness-regression-gate-design.md.
"""

from __future__ import annotations

import pytest


def _results(passed_labels, failed_labels=()):
    from core.engine.eval.grader import CaseResult

    return [CaseResult(label=lbl, passed=True) for lbl in passed_labels] + [
        CaseResult(label=lbl, passed=False) for lbl in failed_labels
    ]


def _baseline(per_case: dict[str, bool]):
    from core.engine.eval.grader import Baseline

    acc = sum(per_case.values()) / len(per_case) if per_case else 1.0
    return Baseline(accuracy=acc, per_case=dict(per_case))


def test_no_baseline_passes_and_reports():
    """First run (no baseline): never fail, but report current accuracy for --update-baseline."""
    from core.engine.eval.grader import grade

    results = _results(["a", "b", "c"], ["d"])
    v = grade(results, None)
    assert v.passed is True
    assert v.regressed is False
    assert v.current_accuracy == pytest.approx(0.75)
    assert v.newly_broken == []


def test_within_tolerance_passes():
    """17/18 vs baseline 18/18 within default tolerance -> pass, not regressed, no newly_broken."""
    from core.engine.eval.grader import grade

    labels = [f"c{i}" for i in range(18)]
    baseline = _baseline({lbl: True for lbl in labels})
    # one case fails now (c17), but it's the ONLY change and within tolerance
    results = _results(labels[:17], [labels[17]])
    v = grade(results, baseline)
    assert v.regressed is False
    # newly_broken makes the gate strict; assert the aggregate path explicitly here:
    assert v.current_accuracy == pytest.approx(17 / 18)
    assert v.baseline_accuracy == pytest.approx(1.0)


def test_beyond_tolerance_regresses():
    """14/18 vs 18/18 is well beyond tolerance -> regressed -> gate fails."""
    from core.engine.eval.grader import grade

    labels = [f"c{i}" for i in range(18)]
    baseline = _baseline({lbl: True for lbl in labels})
    results = _results(labels[:14], labels[14:])
    v = grade(results, baseline)
    assert v.regressed is True
    assert v.passed is False


def test_single_newly_broken_within_budget_passes_but_reported():
    """One case flipping pass->fail in an 18-set is within the variance budget (floor(0.06*18)=1):
    advisory (reported in newly_broken) but does NOT fail the gate — temp-1 noise, not a regression."""
    from core.engine.eval.grader import grade

    labels = [f"c{i}" for i in range(18)]
    base_map = {lbl: True for lbl in labels}
    base_map["c0"] = False  # baseline 17/18
    baseline = _baseline(base_map)
    # c0 fixed, c1 broke -> still 17/18, one newly_broken
    results = _results([lbl for lbl in labels if lbl != "c1"], ["c1"])
    v = grade(results, baseline)
    assert v.current_accuracy == pytest.approx(v.baseline_accuracy)
    assert "c1" in v.newly_broken  # surfaced as actionable diff
    assert v.passed is True, "a single newly-broken case is within the variance budget"


def test_newly_broken_beyond_budget_fails_at_flat_accuracy():
    """Two breaks hidden behind two lucky fixes: aggregate accuracy is flat (tolerance can't see it),
    but gross newly_broken (2) exceeds the budget (1) -> the masked regression fails the gate."""
    from core.engine.eval.grader import grade

    labels = [f"c{i}" for i in range(18)]
    base_map = {lbl: True for lbl in labels}
    base_map["c0"] = False
    base_map["c1"] = False  # baseline 16/18
    baseline = _baseline(base_map)
    # c0,c1 fixed (was fail) but c2,c3 broke -> still 16/18, flat accuracy, 2 newly_broken
    now_failed = ["c2", "c3"]
    results = _results([lbl for lbl in labels if lbl not in now_failed], now_failed)
    v = grade(results, baseline)
    assert v.current_accuracy == pytest.approx(v.baseline_accuracy)
    assert v.regressed is False
    assert set(v.newly_broken) == {"c2", "c3"}
    assert v.passed is False, "newly_broken beyond the variance budget must fail even at flat accuracy"


def test_newly_fixed_detected_and_does_not_fail():
    """fail->pass cases are surfaced as newly_fixed and never fail the gate."""
    from core.engine.eval.grader import grade

    labels = [f"c{i}" for i in range(18)]
    base_map = {lbl: True for lbl in labels}
    base_map["c0"] = False  # was failing
    baseline = _baseline(base_map)
    results = _results(labels)  # all pass now -> c0 fixed
    v = grade(results, baseline)
    assert "c0" in v.newly_fixed
    assert v.newly_broken == []
    assert v.passed is True


def test_empty_results_with_baseline_hard_fails():
    """Runner produced nothing but a baseline exists -> the run broke -> fail, no vacuous pass."""
    from core.engine.eval.grader import grade

    baseline = _baseline({"a": True, "b": True})
    v = grade([], baseline)
    assert v.passed is False


def test_load_baseline_missing_file_returns_none(tmp_path):
    from core.engine.eval.baseline import load_baseline

    assert load_baseline(str(tmp_path / "nope.json")) is None


def test_load_baseline_corrupt_file_raises(tmp_path):
    """A committed-but-unreadable baseline is a defect, not 'no baseline' — must RAISE, never
    degrade to a silent pass (reviewer C1)."""
    from core.engine.eval.baseline import load_baseline

    path = tmp_path / "classifier_routing.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    with pytest.raises(Exception):
        load_baseline(str(path))


def test_baseline_roundtrip(tmp_path):
    from core.engine.eval.baseline import load_baseline, save_baseline
    from core.engine.eval.grader import Baseline

    b = Baseline(accuracy=0.9, per_case={"a": True, "b": False}, generated_at="2026-06-22")
    path = str(tmp_path / "baseline.json")
    save_baseline(path, b)
    loaded = load_baseline(path)
    assert loaded is not None
    assert loaded.accuracy == pytest.approx(0.9)
    assert loaded.per_case == {"a": True, "b": False}
    assert loaded.generated_at == "2026-06-22"
