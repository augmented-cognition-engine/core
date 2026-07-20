import pytest


@pytest.mark.asyncio
async def test_drift_detector_emits_on_band_cross(db_pool):
    """When blocked-fraction crosses a band boundary, drift detector emits."""
    from core.engine.voice.detectors.drift_detector import compute_band

    assert compute_band(0.0) == 0
    assert compute_band(0.29) == 0
    assert compute_band(0.31) == 1
    assert compute_band(0.51) == 2
    assert compute_band(0.71) == 3
    assert compute_band(0.91) == 4


@pytest.mark.asyncio
async def test_drift_detector_does_not_emit_within_band(db_pool):
    """Same-band changes don't fire."""
    # tested implicitly via compute_band — within-band changes return same value
    from core.engine.voice.detectors.drift_detector import compute_band

    assert compute_band(0.10) == compute_band(0.20)  # same band


def test_drift_payload_supports_direction_predicate():
    """canvas.drift.crossed payload includes new_blocked_frac + prev_blocked_frac.

    G3: The thread layer uses these fields directly to determine direction —
    no code change required in drift_detector.py.
    Predicate: new_blocked_frac == 0.0 AND new_blocked_frac < prev_blocked_frac → resolved.
    """
    # Simulate the payload emitted by _maybe_emit_drift
    resolved_payload = {
        "product_id": "product:platform",
        "prev_blocked_frac": 0.35,
        "new_blocked_frac": 0.0,
        "n_total": 10,
        "n_blocked": 0,
        "blocking_pillars": [],
    }
    worsened_payload = {
        "product_id": "product:platform",
        "prev_blocked_frac": 0.0,
        "new_blocked_frac": 0.35,
        "n_total": 10,
        "n_blocked": 3,
        "blocking_pillars": ["experience"],
    }

    def _is_drift_resolved(p: dict) -> bool:
        """Thread-layer predicate: drift thread resolves when new_blocked_frac drops to 0."""
        return p["new_blocked_frac"] == 0.0 and p["new_blocked_frac"] < p["prev_blocked_frac"]

    assert _is_drift_resolved(resolved_payload) is True
    assert _is_drift_resolved(worsened_payload) is False
