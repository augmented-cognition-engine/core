# tests/test_crm_calibrator.py
"""Tests for CrmCalibrator — outcome-conditioned confidence calibration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(rows):
    db = AsyncMock()
    db.query = AsyncMock(return_value=rows)
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


# test_crm_calibrator_computes_stats: groups by discipline, computes avg confidence
@pytest.mark.asyncio
async def test_crm_calibrator_computes_stats():
    # failure_memory records: discipline=api_design, 2 records
    rows = [
        [
            {"discipline": "api_design", "verdict": "gaps_found", "confidence": 0.8},
            {"discipline": "api_design", "verdict": "clean", "confidence": 0.6},
            {"discipline": "testing", "verdict": "gaps_found", "confidence": 0.3},
        ]
    ]
    pool = _make_pool(rows)

    with patch("core.engine.core.db.pool", pool):
        from core.engine.cognition.crm_calibrator import CrmCalibrator

        calibrator = CrmCalibrator(pool)
        report = await calibrator.compute_report("product:test")

    assert "api_design" in report
    assert report["api_design"]["sample_count"] == 2
    # avg failing confidence for api_design = 0.8 (one gaps_found record)
    assert report["api_design"]["avg_failing_confidence"] == pytest.approx(0.8)
    assert "testing" in report
    assert report["testing"]["avg_failing_confidence"] == pytest.approx(0.3)


# test_crm_calibrator_empty: no records → empty report
@pytest.mark.asyncio
async def test_crm_calibrator_empty():
    pool = _make_pool([[]])

    with patch("core.engine.core.db.pool", pool):
        from core.engine.cognition.crm_calibrator import CrmCalibrator

        calibrator = CrmCalibrator(pool)
        report = await calibrator.compute_report("product:test")

    assert report == {}


# test_crm_calibrator_write_stores_report: writes calibration_report record
@pytest.mark.asyncio
async def test_crm_calibrator_write_stores_report():
    db = AsyncMock()
    db.query = AsyncMock(
        side_effect=[
            [  # SELECT failure_memory
                [{"discipline": "security", "verdict": "gaps_found", "confidence": 0.7}]
            ],
            [[]],  # CREATE calibration_report (ignored)
        ]
    )
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm

    with patch("core.engine.core.db.pool", pool):
        from core.engine.cognition.crm_calibrator import CrmCalibrator

        calibrator = CrmCalibrator(pool)
        await calibrator.run("product:test")

    # Should have called query twice: SELECT + CREATE
    assert db.query.call_count == 2
    # Second call should contain "CREATE calibration_report"
    create_call = db.query.call_args_list[1][0][0]
    assert "calibration_report" in create_call


# test_crm_calibrator_missing_confidence_defaults: rows without confidence field use 0.5
@pytest.mark.asyncio
async def test_crm_calibrator_missing_confidence_defaults():
    """Rows without confidence key fall back to 0.5 (neutral)."""
    rows = [
        [
            {"discipline": "security", "verdict": "gaps_found"},  # no confidence key
            {"discipline": "security", "verdict": "gaps_found"},  # no confidence key
        ]
    ]
    pool = _make_pool(rows)

    with patch("core.engine.core.db.pool", pool):
        from core.engine.cognition.crm_calibrator import CrmCalibrator

        calibrator = CrmCalibrator(pool)
        report = await calibrator.compute_report("product:test")

    assert report["security"]["avg_failing_confidence"] == pytest.approx(0.5)
    assert report["security"]["overconfident"] is False  # 0.5 < 0.7
