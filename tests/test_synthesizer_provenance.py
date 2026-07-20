"""Synthesizer provenance threading (the active loop's anti-echo-chamber seam).

A fully self-generated observation batch (reasoning conclusion / composition phase) must tag its
insights with a self-generated provenance kind in source_domain, so the reconciler scores them at the
low trust prior instead of laundering them into capture-tier 0.80. External/human batches are untouched.
Pure helpers — no DB, no LLM.
"""

import pytest

from core.engine.capture.synthesizer import _batch_provenance_kind, _compose_source_domain


@pytest.mark.parametrize(
    "sources,expected",
    [
        (["reasoning_conclusion"], "reasoning"),
        (["reasoning_conclusion", "reasoning_conclusion"], "reasoning"),
        (["composition_phase"], "composition"),
        (["composition_phase", "composition_phase"], "composition"),
        # Mixed self + external -> None: a corroborating human capture must never downgrade the insight.
        (["reasoning_conclusion", "chat"], None),
        (["reasoning_conclusion", "composition_phase"], None),  # two different self-kinds -> ambiguous
        (["chat"], None),
        (["document"], None),
        ([], None),
    ],
)
def test_batch_provenance_kind(sources, expected):
    obs = [{"source": s} for s in sources]
    assert _batch_provenance_kind(obs) == expected


def test_batch_provenance_kind_tolerates_missing_source_field():
    assert _batch_provenance_kind([{"content": "x"}]) is None
    assert _batch_provenance_kind([{"source": None}]) is None


def test_compose_source_domain_encodes_kind_but_leaves_routing_slug():
    # Provenance kind goes into source_domain (kind.<slug>); domain_path stays the bare slug elsewhere.
    assert _compose_source_domain("security", "reasoning") == "reasoning.security"
    assert _compose_source_domain("product_strategy", "composition") == "composition.product_strategy"


def test_compose_source_domain_is_identity_without_kind_or_slug():
    assert _compose_source_domain("security", None) == "security"  # direct capture unchanged
    assert _compose_source_domain("", "reasoning") == ""  # no slug -> nothing to prefix
