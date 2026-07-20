import pytest

from core.engine.canvas import event_protocol as ep


@pytest.mark.unit
def test_phase_event_constants_registered():
    for c in (ep.EVENT_AGENT_PHASE_START, ep.EVENT_AGENT_PHASE_STEP, ep.EVENT_AGENT_PHASE_END):
        assert c in ep.ALL_EVENT_TYPES


@pytest.mark.unit
def test_phase_payloads_serialize():
    start = ep.AgentPhaseStartPayload(phase_idx=0, total_phases=3, cognitive_function="frame")
    step = ep.AgentPhaseStepPayload(phase_idx=0, cognitive_function="frame", content="…")
    end = ep.AgentPhaseEndPayload(phase_idx=0, cognitive_function="frame", confidence=0.7, gaps=[])
    assert start.model_dump()["cognitive_function"] == "frame"
    assert step.model_dump()["content"] == "…"
    assert end.model_dump()["confidence"] == 0.7
