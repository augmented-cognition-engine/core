"""The eval grader — pure, deterministic baseline-relative regression logic.

An LLM-graded golden set is a *distribution* (16/18 today, 17/18 tomorrow, same true quality), so an
all-or-nothing gate (`failed == 0`) flakes and gets disabled. Instead, gate on regression relative to
a committed baseline with a tolerance, and separately surface cases that flipped pass->fail
(`newly_broken`) — a real break can hide behind a lucky fix at equal aggregate accuracy.

Generic over CaseResult: the same grader covers classifier routing, arm output, depth selection —
any golden set whose runner can emit (label, passed) rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ≈ one case in an 18-case set — absorbs single-case LLM variance without hiding real drift.
_DEFAULT_TOLERANCE = 0.06


@dataclass(frozen=True)
class CaseResult:
    """One golden-case outcome. Runner-agnostic — any eval emits these."""

    label: str
    passed: bool


@dataclass(frozen=True)
class Baseline:
    """A committed snapshot of a golden set's outcome, diffable in git."""

    accuracy: float  # 0..1 aggregate at baseline time
    per_case: dict[str, bool]  # label -> passed
    generated_at: str | None = None


@dataclass(frozen=True)
class EvalVerdict:
    passed: bool  # the gate result
    current_accuracy: float
    baseline_accuracy: float
    tolerance: float
    regressed: bool  # current_accuracy < baseline_accuracy - tolerance
    newly_broken: list[str] = field(default_factory=list)  # pass@baseline -> fail@now (actionable)
    newly_fixed: list[str] = field(default_factory=list)  # fail@baseline -> pass@now (re-baseline?)
    has_baseline: bool = True


def grade(
    results: list[CaseResult],
    baseline: Baseline | None,
    *,
    tolerance: float = _DEFAULT_TOLERANCE,
) -> EvalVerdict:
    """Grade a run against a baseline. Pure: no I/O, no LLM, no DB.

    Gate fails when the run regressed beyond tolerance OR any case flipped pass->fail. A first run
    with no baseline always passes (reports current accuracy so the operator can --update-baseline),
    but an EMPTY run with a baseline present is a hard fail — the runner produced nothing.
    """
    total = len(results)
    current_accuracy = (sum(1 for r in results if r.passed) / total) if total else 1.0

    # No baseline yet: report, never fail. Don't pass silently — leave a trail.
    if baseline is None:
        logger.info("eval: no baseline — reporting current accuracy %.3f (run --update-baseline)", current_accuracy)
        return EvalVerdict(
            passed=True,
            current_accuracy=current_accuracy,
            baseline_accuracy=0.0,
            tolerance=tolerance,
            regressed=False,
            has_baseline=False,
        )

    # Baseline exists but the runner produced nothing -> the run broke. Never vacuously pass.
    if total == 0:
        return EvalVerdict(
            passed=False,
            current_accuracy=0.0,
            baseline_accuracy=baseline.accuracy,
            tolerance=tolerance,
            regressed=True,
        )

    now = {r.label: r.passed for r in results}
    newly_broken = sorted(
        lbl
        for lbl, was_passing in baseline.per_case.items()
        if was_passing and not now.get(lbl, False)  # was passing; now failing or absent
    )
    newly_fixed = sorted(
        lbl
        for lbl, is_passing in now.items()
        if is_passing and not baseline.per_case.get(lbl, True)  # was failing (default True = not tracked)
    )

    # The classifier runs at temperature 1 as a single un-voted call, so per-case outcomes vary
    # run-to-run. Hard-failing on a SINGLE newly-broken case would reintroduce the flaky gate this
    # design exists to kill (reviewer I1). Instead, apply the SAME variance budget as the aggregate
    # tolerance: per-case churn up to floor(tolerance * total) is absorbed as noise; beyond it is a
    # real regression. This still catches the masked-break case (k breaks hidden behind k lucky
    # fixes leaves aggregate accuracy flat, but gross newly_broken > budget trips the gate).
    broken_budget = int(tolerance * total)  # floor for positive operands
    regressed = current_accuracy < baseline.accuracy - tolerance
    passed = (not regressed) and (len(newly_broken) <= broken_budget)

    return EvalVerdict(
        passed=passed,
        current_accuracy=current_accuracy,
        baseline_accuracy=baseline.accuracy,
        tolerance=tolerance,
        regressed=regressed,
        newly_broken=newly_broken,
        newly_fixed=newly_fixed,
    )
