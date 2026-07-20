from core.engine.canvas.canvas_ui_events import translate_canvas_event
from core.engine.canvas.event_protocol import EVENT_AGENT_PERSPECTIVE_TOKEN


def test_perspective_token_maps_to_ui_token_delta():
    evt = translate_canvas_event(
        EVENT_AGENT_PERSPECTIVE_TOKEN,
        {"archetype": "analyst", "delta": "hello ", "perspective_index": 1},
        run_id="r1",
        product_id="product:test",
    )
    assert evt is not None
    d = evt.to_dict()
    assert d["type"] == "token"
    assert d["content"] == "hello "
    assert d["task_id"] == "canvas-perspective-1"  # same track id used by start/end
