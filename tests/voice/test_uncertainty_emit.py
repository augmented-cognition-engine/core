import pytest


@pytest.mark.asyncio
async def test_query_uncertainty_emits_canvas_event(monkeypatch, db_pool):
    """query_uncertainty should fire canvas.uncertainty.opened on the bus."""
    captured = []

    async def fake_emit(event_type, payload):
        captured.append((event_type, payload))

    from core.engine.events import bus as bus_singleton

    monkeypatch.setattr(bus_singleton, "emit", fake_emit)

    from core.engine.product.uncertainty import query_uncertainty

    await query_uncertainty(
        db_pool,
        product_id="product:platform",
        scope="ambition",
        question="Is X still in scope?",
        fallback_action="default_safe",
    )

    assert any(et == "canvas.uncertainty.opened" for et, _ in captured)
    payload = next(p for et, p in captured if et == "canvas.uncertainty.opened")
    assert payload.get("product_id") == "product:platform"
    assert "Is X" in payload.get("question", "")
