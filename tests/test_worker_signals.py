def test_signal_emission_fields():
    from core.engine.worker.signals import SignalEmission

    s = SignalEmission(
        kind="intelligence_classified",
        product_id="product:platform",
        payload={"discipline": "ux", "summary": "..."},
        confidence=0.85,
    )
    assert s.kind == "intelligence_classified"
    assert s.confidence == 0.85


import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_extract_signals_returns_empty_when_flag_off(db_pool):
    """extract_signals returns [] when feature flag is off (default)."""
    from core.engine.worker.signals import extract_signals

    signals = await extract_signals("product:platform")
    assert signals == []


@pytest.mark.asyncio
async def test_extract_signals_high_confidence_returns_signal(db_pool):
    """High-confidence insight produces one signal when flag is on."""
    from core.engine.worker.feature_flag import set_worker_canvas_bridge_enabled
    from core.engine.worker.signals import extract_signals

    pid = "product:platform"
    await set_worker_canvas_bridge_enabled(db_pool, pid, True)
    try:
        # Insert a fresh high-confidence insight using schema-valid fields
        async with db_pool.connection() as db:
            await db.query(
                """CREATE insight CONTENT {
                    product: <record>$pid,
                    domain_path: 'testing',
                    source_domain: 'testing',
                    confidence: 0.9,
                    content: 'High-conf insight for signal extraction test',
                    status: 'active',
                    tier: 'subdomain',
                    insight_type: 'fact',
                    created_at: time::now()
                }""",
                {"pid": pid},
            )

        signals = await extract_signals(pid)
        # discipline comes from domain_path since insight table has no discipline_hint field
        assert any(s.kind == "intelligence_classified" and s.payload.get("discipline") == "testing" for s in signals), (
            f"Expected intelligence_classified signal for 'testing', got: {signals}"
        )
    finally:
        await set_worker_canvas_bridge_enabled(db_pool, pid, False)


@pytest.mark.asyncio
async def test_extract_signals_low_confidence_no_signal(db_pool):
    """Low-confidence insight (at or below threshold) produces no signal."""
    from core.engine.worker.feature_flag import set_worker_canvas_bridge_enabled
    from core.engine.worker.signals import extract_signals

    pid = "product:platform"
    await set_worker_canvas_bridge_enabled(db_pool, pid, True)
    try:
        async with db_pool.connection() as db:
            await db.query(
                """CREATE insight CONTENT {
                    product: <record>$pid,
                    domain_path: 'observability',
                    source_domain: 'observability',
                    confidence: 0.5,
                    content: 'Low-conf insight should not emit',
                    status: 'active',
                    tier: 'subdomain',
                    insight_type: 'fact',
                    created_at: time::now()
                }""",
                {"pid": pid},
            )

        signals = await extract_signals(pid)
        observability_signals = [s for s in signals if s.payload.get("discipline") == "observability"]
        assert observability_signals == [], "Low-confidence insight must not emit a signal"
    finally:
        await set_worker_canvas_bridge_enabled(db_pool, pid, False)
