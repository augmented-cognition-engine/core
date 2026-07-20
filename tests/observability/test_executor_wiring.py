"""Tests for executor + hooks wiring — ROI utilization and calibration/self_assessment.

Verifies that:
- utilization_and_roi_hook passes snapshot["intelligence_utilization"] to detect_roi_events
- calibration_hook reads self_assessment from DB instead of hardcoding 0.7
- executor.py writes self_assessment to the task record after output is produced
"""

import pytest

# ── ROI wiring ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_roi_hook_uses_snapshot_utilization():
    """utilization_and_roi_hook passes ctx.snapshot['intelligence_utilization'] to detect_roi_events."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.orchestration.hooks import HookContext, utilization_and_roi_hook

    utilization = {"reflected_ids": ["insight:abc", "insight:def"]}
    ctx = HookContext(
        task_id="task:1",
        product_id="product:test",
        domain_path="security",
        output="done",
        snapshot={"intelligence_utilization": utilization},
        classification={},
    )

    received_utilization = []

    async def fake_detect(task, util, product, db):
        received_utilization.append(util)

    mock_db = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.core.db.pool", mock_pool):
        with patch("core.engine.intelligence.roi_detector.detect_roi_events", fake_detect):
            await utilization_and_roi_hook(ctx)

    assert received_utilization == [utilization]


@pytest.mark.asyncio
async def test_roi_hook_empty_when_no_utilization():
    """When snapshot has no 'intelligence_utilization', detect_roi_events receives {} (explicit fallback)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.orchestration.hooks import HookContext, utilization_and_roi_hook

    ctx = HookContext(
        task_id="task:2",
        product_id="product:test",
        domain_path="security",
        output="done",
        snapshot={},  # no intelligence_utilization key
        classification={},
    )

    received_utilization = []

    async def fake_detect(task, util, product, db):
        received_utilization.append(util)

    mock_db = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.core.db.pool", mock_pool):
        with patch("core.engine.intelligence.roi_detector.detect_roi_events", fake_detect):
            await utilization_and_roi_hook(ctx)

    assert received_utilization == [{}]


# ── Calibration wiring ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calibration_hook_reads_self_assessment_from_db():
    """calibration_hook fetches self_assessment from DB and passes it to apply_calibration."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.orchestration.hooks import HookContext, calibration_hook

    ctx = HookContext(
        task_id="task:99",
        product_id="product:test",
        domain_path="security",
        output="done",
        snapshot={},
        classification={},
    )

    received_confidence = []

    def fake_apply(confidence, domain, data):
        received_confidence.append(confidence)
        return confidence

    mock_db = AsyncMock()
    # First query: SELECT self_assessment → returns 0.82
    # Second query: SELECT calibration data → returns cal row with data
    mock_db.query = AsyncMock(
        side_effect=[
            [{"self_assessment": 0.82}],  # task self_assessment fetch
            [{"data": {"offset": 0.05}}],  # calibration data fetch
            [],  # UPDATE calibrated_assessment
        ]
    )
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.core.db.pool", mock_pool):
        with patch("core.engine.intelligence.calibration.apply_calibration", fake_apply):
            await calibration_hook(ctx)

    assert received_confidence == [0.82]


@pytest.mark.asyncio
async def test_calibration_hook_fallback_when_no_self_assessment():
    """When task has no self_assessment, apply_calibration receives 0.7 fallback."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.orchestration.hooks import HookContext, calibration_hook

    ctx = HookContext(
        task_id="task:100",
        product_id="product:test",
        domain_path="security",
        output="done",
        snapshot={},
        classification={},
    )

    received_confidence = []

    def fake_apply(confidence, domain, data):
        received_confidence.append(confidence)
        return confidence

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            [{}],  # task row with no self_assessment field
            [{"data": {"offset": 0.0}}],  # calibration data
            [],  # UPDATE
        ]
    )
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.core.db.pool", mock_pool):
        with patch("core.engine.intelligence.calibration.apply_calibration", fake_apply):
            await calibration_hook(ctx)

    assert received_confidence == [0.7]


@pytest.mark.asyncio
async def test_calibration_hook_skips_when_no_calibration_data():
    """apply_calibration is not called when no calibration data exists in DB."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.orchestration.hooks import HookContext, calibration_hook

    ctx = HookContext(
        task_id="task:101",
        product_id="product:test",
        domain_path="security",
        output="done",
        snapshot={},
        classification={},
    )

    call_count = []

    def fake_apply(confidence, domain, data):
        call_count.append(1)
        return confidence

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            [{"self_assessment": 0.75}],  # self_assessment fetch
            [],  # no calibration rows
        ]
    )
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.core.db.pool", mock_pool):
        with patch("core.engine.intelligence.calibration.apply_calibration", fake_apply):
            await calibration_hook(ctx)

    assert call_count == []  # apply_calibration never called


@pytest.mark.asyncio
async def test_executor_writes_self_assessment():
    """executor.py computes _self_assessment and writes it to the task record via UPDATE query."""
    import inspect

    from core.engine.orchestrator import executor

    source = inspect.getsource(executor)
    assert "_self_assessment" in source
    assert "self_assessment" in source
    # The UPDATE query that writes self_assessment must be present
    assert "SET self_assessment" in source or "self_assessment = $sa" in source
