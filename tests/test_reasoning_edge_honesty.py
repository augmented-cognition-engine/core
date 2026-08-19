"""System C honesty: inferred reasoning_edges are temporal co-occurrence, not causal claims.

`edge_inference` derives a reasoning_edge whenever ``to_event`` followed ``from_event`` within a time
window with a matching payload field — succession, not causation. Yet the stored ``edge_type`` is
``"triggered"`` (reads as causal) and the module docstring called the links "causal". The graph
assessment (System C) flagged this as the substance behind the Atrium honesty note
(``EntityIntelligence.tsx:409``): these edges carry no causal model.

This test pins the honest semantics as an explicit, checkable contract so nothing — including a
future ambient surfacer — can present these edges as causation without a deliberate, reviewed
change. Renaming the stored ``"triggered"`` type is a data-model migration (a live-backend
follow-up), not part of this in-code honesty pass.
"""

from __future__ import annotations

import pytest

from core.engine.cognition.edge_inference import (
    REASONING_EDGE_IS_CAUSAL,
    REASONING_EDGE_RELATION_SEMANTICS,
    reasoning_edge_relation_semantics,
)

pytestmark = pytest.mark.unit


def test_reasoning_edges_are_declared_not_causal():
    assert REASONING_EDGE_IS_CAUSAL is False


def test_relation_semantics_is_temporal_cooccurrence():
    assert REASONING_EDGE_RELATION_SEMANTICS == "temporal_cooccurrence"


def test_semantics_helper_is_explicit_and_honest():
    semantics = reasoning_edge_relation_semantics()

    assert semantics["is_causal"] is False
    assert semantics["semantics"] == "temporal_cooccurrence"
    # The stored edge_type label is disclosed as a succession label, not a causal claim.
    assert "triggered" in semantics["stored_edge_type_note"].lower()
    assert "causal" in semantics["stored_edge_type_note"].lower()
