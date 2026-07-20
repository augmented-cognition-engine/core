from core.engine.cognition.confidence_gate import ConfidenceGate
from core.engine.cognition.phase_output import PhaseOutput


def test_gate_fires_on_low_confidence():
    gate = ConfidenceGate()
    po = PhaseOutput(output="analysis", confidence=0.4, evidence=[], gaps=[])
    assert gate.should_retrieve(po) is True


def test_gate_fires_on_gaps():
    gate = ConfidenceGate()
    po = PhaseOutput(output="analysis", confidence=0.9, evidence=[], gaps=["unclear requirement"])
    assert gate.should_retrieve(po) is True


def test_gate_does_not_fire_on_clean_output():
    gate = ConfidenceGate()
    po = PhaseOutput(output="analysis", confidence=0.8, evidence=["fact A"], gaps=[])
    assert gate.should_retrieve(po) is False


def test_gate_respects_custom_threshold():
    gate = ConfidenceGate(confidence_threshold=0.9)
    po = PhaseOutput(output="x", confidence=0.85, evidence=[], gaps=[])
    assert gate.should_retrieve(po) is True  # 0.85 < 0.9


def test_retrieval_query_returns_gap_terms():
    gate = ConfidenceGate()
    po = PhaseOutput(output="x", confidence=0.5, evidence=[], gaps=["gap A", "gap B", "gap C"])
    terms = gate.retrieval_query(po)
    assert "gap A" in terms
    assert "gap B" in terms
    assert "gap C" in terms


def test_retrieval_query_capped_at_five():
    gate = ConfidenceGate()
    po = PhaseOutput(output="x", confidence=0.3, evidence=[], gaps=[f"gap {i}" for i in range(10)])
    terms = gate.retrieval_query(po)
    assert len(terms) <= 5
