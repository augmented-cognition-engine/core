"""The ambient code-intelligence gate decides *when* to surface, before any engine call.

The gate is the first stage of the A0 ambient trigger (Decision 15 / the intelligence-builder-OS
north star). It is deliberately engine-independent: it answers "should we consult code intelligence
for this turn, and with what query?" without touching the graph. Two invariants it must hold:

  1. Skip when there is no graph substrate (the north star's "baked in but gated — activate only
     where it has substrate"). A personal user with no repo must see zero ambient code-intel work.
  2. Skip turns that are not code-intelligence-shaped (gate precision — firing on every turn floods
     context and degrades the model).
"""

from __future__ import annotations

import pytest

from ace_mcp_client.ambient import AmbientEvent, gate

pytestmark = pytest.mark.unit


def test_gate_skips_when_no_graph_substrate():
    # A clearly code-shaped question, but nothing to answer it from.
    decision = gate(AmbientEvent(prompt="why is the scanner built this way?", graph_in_scope=False))

    assert decision.fire is False
    assert "substrate" in decision.reason.lower()
    assert decision.query is None


def test_gate_skips_non_code_shaped_turn():
    decision = gate(AmbientEvent(prompt="what should I make for dinner tonight?", graph_in_scope=True))

    assert decision.fire is False
    assert decision.query is None


def test_gate_fires_on_code_shaped_turn_with_graph():
    decision = gate(AmbientEvent(prompt="why is core/engine/scanner.py built this way?", graph_in_scope=True))

    assert decision.fire is True
    # The extracted query carries the turn's intent forward to the engine stage.
    assert decision.query
    assert "scanner" in decision.query.lower()


def test_gate_fires_on_rationale_question_without_a_path():
    # "why … built this way" is a decision-trail cue even without an explicit file path.
    decision = gate(AmbientEvent(prompt="what is the architecture here and why was it decided?", graph_in_scope=True))

    assert decision.fire is True
