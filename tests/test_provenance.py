"""Pure provenance helpers: parse_source, trust_prior, trust_score."""

import pytest

from core.engine.capture.provenance import TRUST_PRIORS, parse_source, trust_prior, trust_score


@pytest.mark.parametrize(
    "source_domain,expected",
    [
        ("human.conflict-resolution", ("human", "conflict-resolution")),
        ("sentinel.domain_research", ("sentinel", "domain_research")),
        ("sentinel.intelligence_optimizer", ("sentinel", "intelligence_optimizer")),
        ("research.arxiv-2401", ("research", "arxiv-2401")),
        ("architecture", ("capture", "architecture")),
        ("", ("unknown", "")),
        ("weirdprefix.detail", ("unknown", "weirdprefix.detail")),
        # Self-generated kinds (the active loop) — recognized so trust scores at the self-generated prior.
        ("reasoning.security", ("reasoning", "security")),
        ("composition.product_strategy", ("composition", "product_strategy")),
    ],
)
def test_parse_source(source_domain, expected):
    assert parse_source(source_domain) == expected


def test_self_generated_kinds_sit_below_every_external_source():
    """Echo-chamber guard: a self-generated insight must never out-trust an externally-grounded one."""
    external = ["human", "capture", "consolidation", "sentinel", "research", "import"]
    for kind in ("reasoning", "composition"):
        assert trust_prior(kind) == 0.50
        assert all(trust_prior(kind) < trust_prior(ext) for ext in external)


def test_trust_prior_known_kinds():
    assert trust_prior("human") == 0.95
    assert trust_prior("capture") == 0.80
    assert trust_prior("sentinel") == 0.65
    assert trust_prior("research") == 0.55


def test_trust_prior_unknown_defaults():
    assert trust_prior("not_a_kind") == 0.60
    assert trust_prior("unknown") == 0.60


def test_trust_score_neutral_seams_equals_prior():
    for kind in TRUST_PRIORS:
        assert trust_score(kind) == trust_prior(kind)


def test_trust_score_composition_and_clamp():
    assert trust_score("human", propagation=0.5) == pytest.approx(0.475)
    assert trust_score("human", corroboration=2.0) == 1.0
    assert trust_score("research", propagation=0.0) == 0.0
    assert trust_score("capture", track_record=0.5, decay=0.5) == pytest.approx(0.2)
