from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DEFINITION = (
    "ACE provides graph-grounded, calibrated foresight. It projects conditional consequences of "
    "decisions, exposes the mechanisms and uncertainty behind them, observes what actually happens, "
    "and uses resolved forecasts to improve later reasoning."
)


def _normalized(path: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    text = re.sub(r"[*_`]", "", text)
    return " ".join(text.split())


def test_canonical_foresight_definition_is_consistent() -> None:
    for path in ("README.md", "ROADMAP.md", "docs/architecture.md", "docs/foresight.md"):
        assert CANONICAL_DEFINITION in _normalized(path), path


def test_public_product_copy_does_not_claim_a_world_model() -> None:
    for path in (
        "README.md",
        "core/engine/foresight/__init__.py",
        "core/ui/canvas/src/app/fixtures/multiplayer.tsx",
    ):
        assert re.search(r"\bworld[- ]model\b", _normalized(path), flags=re.IGNORECASE) is None, path


def test_f1_roadmap_state_and_target_contract_are_explicit() -> None:
    roadmap = _normalized("ROADMAP.md")
    status = _normalized("docs/roadmap-status.md")
    contract = _normalized("docs/foresight.md")
    evidence = _normalized("docs/f1-foresight-evidence.md")

    assert "| F1 | passed |" in roadmap
    assert "| F1 | Next | passed |" in status
    assert "| L1 | not ready | Use resolved conditional forecasts" in roadmap
    assert "F1 is passed; requires I3 material-use evidence" in roadmap
    assert "F1 v1 proper scoring is deliberately scoped to continuous numeric deltas" in evidence
    assert "The fourth sample creates one plan-linked Comparator Observation v1" in evidence
    assert "The next existential milestone is L1" in evidence

    for required in (
        "no-action baseline",
        "mechanism linking the decision to the consequence",
        "supporting evidence, analogous settled cases, and provenance",
        "confirmed, contradicted, mixed, unresolved, invalid, or still open",
        "ace.foresight.intervention-observation/v1",
        "ace.foresight.indicator-observation/v1",
        "ace.foresight.outside-view-baseline/v1",
        "ace.foresight.prediction-score/v1",
        "ace.foresight.comparator-observation/v1",
        "ace.foresight.comparator-plan/v1",
        "difference-in-differences",
        "never required to create a cold-start forecast",
        "evidence status is plan only, not observed",
        "sample size state is not estimated",
        "Plan-to-Observation Linkage v1",
        "aligned, partially aligned, not aligned, or not planned",
        "No alignment state independently verifies randomization or establishes causality",
        "Indicators without a valid structured rule remain explicitly manual",
        "not a causal estimate and not a no-action counterfactual",
        "zero local cases remain useful",
        "never make a forecast incomplete",
        "model confidence is not reinterpreted as interval coverage",
        "Binary Brier scoring, categorical scoring, reliability curves",
        "Repeating an identical request returns the existing observation",
        "multi-product isolation and redaction behavior",
        "no-foresight, naive/base-rate, and model-only baselines",
    ):
        assert required in contract
