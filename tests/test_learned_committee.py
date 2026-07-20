# tests/test_learned_committee.py
"""Phase 1 — wire the learned committee (preferred_lens_set into selection).

score_lens_composition learns, per problem-class (discipline), which COMBINATION
of tentacles (lenses) historically wins (preferred_lens_set: 5+ signals, mean
outcome > 0.6). That signal was computed every run and discarded. resolve_committee_lenses
now consumes it: a proven winning committee outranks per-lens weighting. Fail-open
to the rule-based + weighted set when there is no learned signal.
"""

from core.engine.orchestration.composition_scorer import (
    ScoredLensComposition,
    resolve_committee_lenses,
)
from core.engine.orchestration.deep_committee import MAX_LENSES


def _cls(discipline="architecture", **kw):
    return {"discipline": discipline, **kw}


def test_no_learned_signal_returns_base_unchanged():
    """Cold/low-signal: the rule-based set passes through untouched (fail-open)."""
    out = resolve_committee_lenses(["architecture", "data"], ScoredLensComposition(), _cls())
    assert out == ["architecture", "data"]


def test_low_weight_lens_is_dropped():
    scored = ScoredLensComposition(lens_weights={"data": 0.05})  # below MIN_WEIGHT (0.1)
    out = resolve_committee_lenses(["architecture", "data"], scored, _cls())
    assert out == ["architecture"]


def test_effective_lens_is_injected():
    scored = ScoredLensComposition(injected_lenses=["security"])
    out = resolve_committee_lenses(["architecture"], scored, _cls())
    assert "architecture" in out and "security" in out


def test_preferred_lens_set_overrides_and_keeps_primary():
    """A proven winning tentacle-set is convened, overriding the weighted base —
    and the primary discipline is always kept."""
    scored = ScoredLensComposition(preferred_lens_set=["data", "security"])
    out = resolve_committee_lenses(["architecture", "performance"], scored, _cls(discipline="architecture"))
    assert out[0] == "architecture"  # primary always present, first
    assert "data" in out and "security" in out
    assert "performance" not in out  # the weighted base set was overridden by the learned winner


def test_preferred_lens_set_does_not_duplicate_primary():
    scored = ScoredLensComposition(preferred_lens_set=["architecture", "data"])
    out = resolve_committee_lenses(["architecture", "performance"], scored, _cls(discipline="architecture"))
    assert out == ["architecture", "data"]


def test_preferred_lens_set_capped_at_max():
    scored = ScoredLensComposition(preferred_lens_set=["a", "b", "c", "d", "e", "f"])
    out = resolve_committee_lenses(["architecture"], scored, _cls(discipline="architecture"))
    assert len(out) <= MAX_LENSES
    assert out[0] == "architecture"


def test_preferred_lens_set_primary_not_first_is_reordered():
    """Primary must be FIRST even when it appears mid-list in the learned set
    (and must not be duplicated)."""
    scored = ScoredLensComposition(preferred_lens_set=["data", "architecture", "security"])
    out = resolve_committee_lenses(["architecture"], scored, _cls(discipline="architecture"))
    assert out[0] == "architecture"
    assert out.count("architecture") == 1
    assert out == ["architecture", "data", "security"]


def test_weighted_base_is_capped_at_max():
    """The weighted-base (no preferred set) path enforces MAX_LENSES even when
    base_lenses already exceeds it — the function honors its own contract."""
    base = ["a", "b", "c", "d", "e", "f"]
    out = resolve_committee_lenses(base, ScoredLensComposition(), _cls())
    assert len(out) <= MAX_LENSES
    assert out == base[:MAX_LENSES]
