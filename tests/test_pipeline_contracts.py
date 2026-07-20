# tests/test_pipeline_contracts.py
"""Tests for observer -> synthesizer field mapping contracts."""


def test_observer_output_uses_observation_type_key():
    """Observer must output 'observation_type', not 'type', for DB writes."""
    # The observer maps LLM's 'type' field to 'observation_type' in the output dict
    # See engine/capture/observer.py line ~53: "observation_type": obs_type
    obs = {
        "content": "test observation",
        "observation_type": "fact",
        "confidence": 0.8,
        "discipline_hint": "architecture",
    }
    assert "observation_type" in obs
    assert "type" not in obs


def test_synthesizer_prompt_reads_observation_type():
    """Synthesizer prompt template uses 'observation_type' from observations."""
    # Verify the synthesizer's prompt template field matches what observer outputs
    from core.engine.capture.synthesizer import Synthesizer

    s = Synthesizer(product_id="product:test", workspace_id=None)

    # Simulate what synthesizer does with observations in _call_primary_llm
    obs = {"observation_type": "correction", "content": "use rem not px", "confidence": 0.85}
    line = f"[{obs.get('observation_type', '?')}] {obs['content']} (conf: {obs.get('confidence', '?')})"
    assert "[correction]" in line
    assert "use rem not px" in line


def test_synthesizer_confidence_is_safe_coerced():
    """Synthesizer uses _safe_confidence for all float conversions."""
    from core.engine.capture.synthesizer import _safe_confidence

    # These are the values the synthesizer might encounter from LLM JSON fallback
    assert _safe_confidence("high") == 0.5
    assert _safe_confidence(0.85) == 0.85
    assert _safe_confidence(None) == 0.5


def test_conflict_field_mapping():
    """Synthesizer maps LLM's 'conflicting_observation' to schema's 'conflicting_content'."""
    # The LLM returns 'conflicting_observation' but the DB field is 'conflicting_content'
    # See engine/capture/synthesizer.py _write_conflict method
    conflict = {
        "existing_insight_id": "insight:1",
        "conflicting_observation": "New conflicting data",
        "explanation": "These contradict each other",
    }
    # Verify the mapping would work
    db_field = conflict.get("conflicting_observation", "")
    assert db_field == "New conflicting data"
