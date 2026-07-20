import pytest

from core.engine.canvas.intent_router import ResponseType, route


def _c(**kw):
    base = {"complexity": "moderate", "task_type": "analyze", "discipline": "strategy"}
    base.update(kw)
    return base


@pytest.mark.unit
def test_ambiguous_routes_to_angle():
    assert route(_c(complexity="ambiguous")) is ResponseType.ANGLE


@pytest.mark.unit
def test_simple_note_routes_to_sticky():
    assert route(_c(complexity="simple", task_type="communicate")) is ResponseType.STICKY


@pytest.mark.unit
def test_decision_routes_to_matrix():
    assert route(_c(task_type="evaluate")) is ResponseType.TRADE_OFF_MATRIX


@pytest.mark.unit
def test_design_routes_to_design_options():
    assert route(_c(task_type="design")) is ResponseType.DESIGN_OPTIONS


@pytest.mark.unit
def test_code_structure_routes_to_code():
    assert route(_c(discipline="technology", task_type="implement")) is ResponseType.CODE_ARCHITECTURE


@pytest.mark.unit
def test_everything_else_routes_to_reasoning():
    assert route(_c(discipline="strategy", task_type="strategic")) is ResponseType.REASONING
