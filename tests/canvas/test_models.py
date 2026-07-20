# tests/canvas/test_models.py
from core.engine.canvas.models import (
    CanvasSession,
    ParticipantState,
    ShapeKind,
)


def test_canvas_session_minimal():
    s = CanvasSession(id="canvas_session:abc", project_id="p1", title="Postgres or Dynamo?")
    assert s.project_id == "p1"
    assert s.created_at is not None  # default factory


def test_participant_state_machine_values():
    assert ParticipantState.IDLE.value == "idle"
    assert set(ParticipantState).issuperset(
        {
            ParticipantState.IDLE,
            ParticipantState.WATCHING,
            ParticipantState.DRAFTING,
            ParticipantState.BLOCKED_ON_INPUT,
        }
    )


def test_artifact_shape_kinds_match_v1_inventory():
    """v1 ships exactly four custom shapes plus generic primitives."""
    custom = {
        ShapeKind.PARTICIPANT_CARD,
        ShapeKind.FRAMEWORK_ARTIFACT,
        ShapeKind.DECISION_STICKY,
        ShapeKind.LINEAGE_EDGE,
    }
    assert custom.issubset(set(ShapeKind))
