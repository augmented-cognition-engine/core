from core.engine.canvas.event_protocol import (
    EVENT_AGENT_PERSPECTIVE_TOKEN,
    AgentPerspectiveTokenPayload,
)


def test_perspective_token_event_and_payload():
    assert EVENT_AGENT_PERSPECTIVE_TOKEN == "agent.perspective.token"
    p = AgentPerspectiveTokenPayload(archetype="analyst", delta="hello ", perspective_index=2)
    d = p.model_dump()
    assert d == {"archetype": "analyst", "delta": "hello ", "perspective_index": 2}
