# tests/canvas/test_event_protocol.py
from core.engine.canvas.event_protocol import (
    EVENT_SESSION_OPENED,
    DecisionMadePayload,
    FrameworkRequestedPayload,
    is_surface_agnostic,
)


def test_event_types_are_strings_not_enums():
    """Surfaces in different languages must be able to emit events.
    Use string constants, not Python-only enums."""
    assert isinstance(EVENT_SESSION_OPENED, str)
    assert EVENT_SESSION_OPENED == "session.opened"


def test_payload_models_have_no_canvas_specific_required_fields():
    """A meeting-transcript surface must be able to emit FrameworkRequested
    without inventing a tldraw_shape_id. Canvas-specific fields must be optional."""
    p = FrameworkRequestedPayload(
        framework_kind="trade_off_matrix",
        prompt="Postgres or DynamoDB?",
        cited_artifact_ids=[],
    )
    assert p.framework_kind == "trade_off_matrix"


def test_decision_made_carries_surface_and_lineage():
    p = DecisionMadePayload(
        title="Use Postgres",
        rationale="Stronger consistency, team familiarity",
        cited_artifact_ids=["art1", "art2"],
        framework_kind="trade_off_matrix",
    )
    assert p.cited_artifact_ids == ["art1", "art2"]


def test_is_surface_agnostic_validates_event_dict():
    """Validator enforces all three surface-agnostic invariants."""
    valid = {"event_type": "session.opened", "surface": "canvas", "payload": {}}
    assert is_surface_agnostic(valid) is True
    # Missing surface
    assert is_surface_agnostic({"event_type": "session.opened", "payload": {}}) is False
    # Empty surface string
    assert is_surface_agnostic({"event_type": "session.opened", "surface": "", "payload": {}}) is False
    # None surface
    assert is_surface_agnostic({"event_type": "session.opened", "surface": None, "payload": {}}) is False
    # Unknown event_type
    assert is_surface_agnostic({"event_type": "bogus.event", "surface": "canvas", "payload": {}}) is False
    # Non-dict payload
    assert is_surface_agnostic({"event_type": "session.opened", "surface": "canvas", "payload": "bad"}) is False


def test_new_event_constants_exist():
    from core.engine.canvas.event_protocol import (
        EVENT_AGENT_PERSPECTIVE_END,
        EVENT_AGENT_PERSPECTIVE_START,
        EVENT_AGENT_PERSPECTIVE_STEP,
        EVENT_SYNTHESIS_END,
        EVENT_SYNTHESIS_START,
        EVENT_SYNTHESIS_STEP,
    )

    assert EVENT_AGENT_PERSPECTIVE_START == "agent.perspective.start"
    assert EVENT_AGENT_PERSPECTIVE_STEP == "agent.perspective.step"
    assert EVENT_AGENT_PERSPECTIVE_END == "agent.perspective.end"
    assert EVENT_SYNTHESIS_START == "synthesis.start"
    assert EVENT_SYNTHESIS_STEP == "synthesis.step"
    assert EVENT_SYNTHESIS_END == "synthesis.end"


def test_new_events_in_all_event_types():
    from core.engine.canvas.event_protocol import ALL_EVENT_TYPES

    assert "agent.perspective.start" in ALL_EVENT_TYPES
    assert "agent.perspective.step" in ALL_EVENT_TYPES
    assert "agent.perspective.end" in ALL_EVENT_TYPES
    assert "synthesis.start" in ALL_EVENT_TYPES
    assert "synthesis.step" in ALL_EVENT_TYPES
    assert "synthesis.end" in ALL_EVENT_TYPES


def test_agent_perspective_start_payload():
    from core.engine.canvas.event_protocol import AgentPerspectiveStartPayload

    p = AgentPerspectiveStartPayload(
        archetype="analyst", mode="deliberative", perspective_index=0, total_perspectives=2
    )
    assert p.archetype == "analyst"
    assert p.total_perspectives == 2


def test_agent_perspective_step_payload():
    from core.engine.canvas.event_protocol import AgentPerspectiveStepPayload

    p = AgentPerspectiveStepPayload(archetype="sentinel", content="risk found", perspective_index=1)
    assert p.content == "risk found"


def test_agent_perspective_end_payload():
    from core.engine.canvas.event_protocol import AgentPerspectiveEndPayload

    p = AgentPerspectiveEndPayload(archetype="creator", handoff="build option A", confidence=0.85, perspective_index=0)
    assert p.confidence == 0.85


def test_synthesis_step_payload():
    from core.engine.canvas.event_protocol import SynthesisStepPayload

    p = SynthesisStepPayload(content="synthesized output")
    assert p.content == "synthesized output"


def test_pipeline_event_constants_exist():
    from core.engine.canvas.event_protocol import (
        EVENT_PIPELINE_CLASSIFY,
        EVENT_PIPELINE_ORCHESTRATE,
    )

    assert EVENT_PIPELINE_CLASSIFY == "pipeline.classify"
    assert EVENT_PIPELINE_ORCHESTRATE == "pipeline.orchestrate"


def test_pipeline_events_in_all_event_types():
    from core.engine.canvas.event_protocol import ALL_EVENT_TYPES

    assert "pipeline.classify" in ALL_EVENT_TYPES
    assert "pipeline.orchestrate" in ALL_EVENT_TYPES


def test_pipeline_classify_payload():
    from core.engine.canvas.event_protocol import PipelineClassifyPayload

    p = PipelineClassifyPayload(
        discipline="architecture",
        archetype="analyst",
        mode="deliberative",
        specialties=["api_design", "testing"],
    )
    assert p.discipline == "architecture"
    assert p.specialties == ["api_design", "testing"]


def test_pipeline_classify_payload_defaults_specialties():
    from core.engine.canvas.event_protocol import PipelineClassifyPayload

    p = PipelineClassifyPayload(discipline="ux", archetype="creator", mode="exploratory")
    assert p.specialties == []


def test_pipeline_orchestrate_payload():
    from core.engine.canvas.event_protocol import PipelineOrchestratePayload

    p = PipelineOrchestratePayload(perspectives=["analyst", "sentinel", "advisor"], total=3)
    assert p.total == 3
    assert "sentinel" in p.perspectives


def test_pipeline_classify_is_surface_agnostic():
    from core.engine.canvas.event_protocol import is_surface_agnostic

    valid = {"event_type": "pipeline.classify", "surface": "canvas", "payload": {}}
    assert is_surface_agnostic(valid) is True


def test_pipeline_orchestrate_is_surface_agnostic():
    from core.engine.canvas.event_protocol import is_surface_agnostic

    valid = {"event_type": "pipeline.orchestrate", "surface": "canvas", "payload": {}}
    assert is_surface_agnostic(valid) is True


def test_pipeline_compose_constant_exists():
    from core.engine.canvas.event_protocol import EVENT_PIPELINE_COMPOSE

    assert EVENT_PIPELINE_COMPOSE == "pipeline.compose"


def test_pipeline_compose_in_all_event_types():
    from core.engine.canvas.event_protocol import ALL_EVENT_TYPES

    assert "pipeline.compose" in ALL_EVENT_TYPES


def test_pipeline_compose_payload():
    from core.engine.canvas.event_protocol import PipelineComposePayload

    p = PipelineComposePayload(
        meta_skills=["coding_intelligence", "planning_intelligence"],
        depth=2,
        fusion_mode=True,
        phase_count=4,
        top_functions=["FRAME", "PRIORITIZE", "VERIFY"],
    )
    assert p.depth == 2
    assert p.fusion_mode is True
    assert "coding_intelligence" in p.meta_skills
    assert p.phase_count == 4


def test_pipeline_compose_is_surface_agnostic():
    from core.engine.canvas.event_protocol import is_surface_agnostic

    valid = {"event_type": "pipeline.compose", "surface": "canvas", "payload": {}}
    assert is_surface_agnostic(valid) is True
