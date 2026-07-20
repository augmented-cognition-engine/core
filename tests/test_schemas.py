# tests/test_schemas.py
import pytest
from pydantic import ValidationError


def test_observation_item_valid():
    from core.engine.capture.schemas import ObservationItem

    item = ObservationItem(content="Token naming uses kebab-case", type="fact", confidence=0.9)
    assert item.content == "Token naming uses kebab-case"
    assert item.type == "fact"
    assert item.confidence == 0.9
    assert item.discipline_hint is None
    assert item.domain_hint is None


def test_observation_item_discipline_hint():
    from core.engine.capture.schemas import ObservationItem

    item = ObservationItem(content="test", type="fact", confidence=0.8, discipline_hint="architecture")
    assert item.discipline_hint == "architecture"


def test_observation_item_domain_hint_backfills_discipline_hint():
    """Backward compat: domain_hint provided alone should backfill discipline_hint."""
    from core.engine.capture.schemas import ObservationItem

    item = ObservationItem(content="test", type="fact", confidence=0.8, domain_hint="architecture")
    assert item.domain_hint == "architecture"
    assert item.discipline_hint == "architecture"


def test_observation_item_rejects_invalid_type():
    from core.engine.capture.schemas import ObservationItem

    with pytest.raises(ValidationError):
        ObservationItem(content="test", type="invalid_type", confidence=0.5)


def test_observation_item_rejects_out_of_range_confidence():
    from core.engine.capture.schemas import ObservationItem

    with pytest.raises(ValidationError):
        ObservationItem(content="test", type="fact", confidence=1.5)


def test_observer_output_valid():
    from core.engine.capture.schemas import ObserverOutput

    output = ObserverOutput(
        has_intelligence=True, observations=[{"content": "test", "type": "decision", "confidence": 0.8}]
    )
    assert output.has_intelligence is True
    assert len(output.observations) == 1


def test_observer_output_empty():
    from core.engine.capture.schemas import ObserverOutput

    output = ObserverOutput(has_intelligence=False, observations=[])
    assert output.observations == []


def test_synthesizer_output_valid():
    from core.engine.capture.schemas import SynthesizerOutput

    output = SynthesizerOutput(
        new_insights=[
            {
                "content": "test",
                "tier": "subdomain",
                "domain_path": "architecture",
                "insight_type": "fact",
                "confidence": 0.8,
                "clearance": "open",
                "source_observations": [0],
            }
        ],
        updates=[],
        conflicts=[],
        skipped=[],
    )
    assert len(output.new_insights) == 1


def test_schemas_produce_json_schema():
    from core.engine.capture.schemas import ObserverOutput, SynthesizerOutput

    obs_schema = ObserverOutput.model_json_schema()
    synth_schema = SynthesizerOutput.model_json_schema()
    assert obs_schema["type"] == "object"
    assert synth_schema["type"] == "object"
