# tests/test_decay_manager.py
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest


def test_get_decay_config_version_tag():
    """Insights tagged 'version' get 14-day threshold, 0.05 decay rate."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config(["version", "react"])
    assert config["threshold_days"] == 14
    assert config["decay_rate"] == 0.05


def test_get_decay_config_personnel_tag():
    """Insights tagged 'personnel' get 30-day threshold, 0.03 decay rate."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config(["personnel"])
    assert config["threshold_days"] == 30
    assert config["decay_rate"] == 0.03


def test_get_decay_config_decision_tag():
    """Insights tagged 'decision' get 365-day threshold, 0.003 decay rate."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config(["decision"])
    assert config["threshold_days"] == 365
    assert config["decay_rate"] == 0.003


def test_get_decay_config_process_tag():
    """Insights tagged 'process' get 180-day threshold, 0.005 decay rate."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config(["process"])
    assert config["threshold_days"] == 180
    assert config["decay_rate"] == 0.005


def test_get_decay_config_regulation_tag():
    """Insights tagged 'regulation' get 90-day threshold, 0.01 decay rate."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config(["regulation"])
    assert config["threshold_days"] == 90
    assert config["decay_rate"] == 0.01


def test_get_decay_config_pricing_tag():
    """Insights tagged 'pricing' get 30-day threshold, 0.03 decay rate."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config(["pricing"])
    assert config["threshold_days"] == 30
    assert config["decay_rate"] == 0.03


def test_get_decay_config_fact_tag():
    """Insights tagged 'fact' get 90-day threshold, 0.01 decay rate."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config(["fact"])
    assert config["threshold_days"] == 90
    assert config["decay_rate"] == 0.01


def test_get_decay_config_unknown_tags_use_default():
    """Insights without recognized category tags use default 0.01/day rate."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config(["random", "unrecognized"])
    assert config["threshold_days"] == 90
    assert config["decay_rate"] == 0.01


def test_get_decay_config_empty_tags_use_default():
    """Insights with no tags use default config."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config([])
    assert config["threshold_days"] == 90
    assert config["decay_rate"] == 0.01


def test_get_decay_config_multiple_tags_uses_first_match():
    """When multiple category tags match, use the first recognized one."""
    from core.engine.sentinel.decay_manager import get_decay_config

    config = get_decay_config(["version", "decision"])
    # 'version' is checked first in priority order
    assert config["threshold_days"] == 14
    assert config["decay_rate"] == 0.05


def test_apply_decay_reduces_confidence():
    """apply_decay reduces confidence by the decay rate, floored at 0.0."""
    from core.engine.sentinel.decay_manager import apply_decay

    assert apply_decay(0.8, 0.05) == 0.75
    assert apply_decay(0.03, 0.05) == 0.0
    assert apply_decay(0.0, 0.01) == 0.0


def test_should_decay_stale_insight():
    """Insight whose last_confirmed is older than threshold should decay."""
    from core.engine.sentinel.decay_manager import should_decay

    now = datetime.now(timezone.utc)
    old_confirmed = now - timedelta(days=20)
    assert should_decay(old_confirmed, threshold_days=14, now=now) is True


def test_should_not_decay_fresh_insight():
    """Recently confirmed insight should not decay."""
    from core.engine.sentinel.decay_manager import should_decay

    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=5)
    assert should_decay(recent, threshold_days=14, now=now) is False


def test_is_ttl_expired_past_ttl():
    """Insight past its TTL should be flagged as expired."""
    from core.engine.sentinel.decay_manager import is_ttl_expired

    now = datetime.now(timezone.utc)
    created = now - timedelta(days=40)
    assert is_ttl_expired(created, ttl_seconds=30 * 86400, now=now) is True


def test_is_ttl_expired_within_ttl():
    """Insight within TTL should not be expired."""
    from core.engine.sentinel.decay_manager import is_ttl_expired

    now = datetime.now(timezone.utc)
    created = now - timedelta(days=10)
    assert is_ttl_expired(created, ttl_seconds=30 * 86400, now=now) is False


def test_is_ttl_expired_no_ttl():
    """Insight with no TTL never expires by TTL."""
    from core.engine.sentinel.decay_manager import is_ttl_expired

    now = datetime.now(timezone.utc)
    created = now - timedelta(days=9999)
    assert is_ttl_expired(created, ttl_seconds=None, now=now) is False


@pytest.mark.asyncio
async def test_run_decay_engine_processes_insights():
    """run() queries active insights, applies decay, returns summary."""

    now = datetime.now(timezone.utc)
    stale = (now - timedelta(days=100)).isoformat()
    fresh = (now - timedelta(days=1)).isoformat()

    mock_db = AsyncMock()
    # First call: SELECT active insights
    mock_db.query = AsyncMock(
        side_effect=[
            # Query 1: select active insights
            [
                [
                    {
                        "id": "insight:a",
                        "tags": ["version"],
                        "confidence": 0.8,
                        "decay_rate": 0.05,
                        "last_confirmed": stale,
                        "created_at": stale,
                        "ttl": None,
                        "status": "active",
                    },
                    {
                        "id": "insight:b",
                        "tags": ["decision"],
                        "confidence": 0.9,
                        "decay_rate": 0.003,
                        "last_confirmed": fresh,
                        "created_at": fresh,
                        "ttl": None,
                        "status": "active",
                    },
                ]
            ],
            # Query 2: UPDATE for insight:a (decayed)
            [{"id": "insight:a"}],
        ]
    )

    from core.engine.sentinel.decay_manager import _run_decay

    result = await _run_decay(mock_db, "product:test")

    assert result["insights_checked"] == 2
    assert result["insights_decayed"] == 1  # insight:a is stale
    assert result["insights_expired"] == 0
