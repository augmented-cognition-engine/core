def test_render_context_defaults():
    from core.engine.voice.render_context import RenderContext

    ctx = RenderContext()
    assert ctx.thread is None
    assert ctx.recent_emissions == []
    assert ctx.salience_policy is None
    assert ctx.fresh_payload_hash is None
    assert ctx.channel == "default"
    assert ctx.calibration_mode == "live"
