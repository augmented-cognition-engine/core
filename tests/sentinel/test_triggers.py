"""Tests for engine/sentinel/triggers.py — reusable trigger primitives."""

from unittest.mock import patch

import pytest


@pytest.mark.unit
async def test_meaningful_change_returns_true_when_mutations_above_threshold():
    """When recent_mutations_since_last_run > threshold, trigger fires."""
    from core.engine.sentinel import triggers

    async def _fake_last(*a, **k):
        return "2026-05-20T00:00:00Z"

    async def _fake_count(*a, **k):
        return 17  # above default threshold of 5

    with (
        patch.object(triggers, "_last_successful_run_time", _fake_last),
        patch.object(triggers, "_count_mutations_since", _fake_count),
    ):
        result = await triggers.meaningful_change_since_last_run("briefing_generator", "product:platform")
    assert result is True


@pytest.mark.unit
async def test_meaningful_change_returns_false_when_below_threshold():
    from core.engine.sentinel import triggers

    async def _fake_last(*a, **k):
        return "2026-05-20T00:00:00Z"

    async def _fake_count(*a, **k):
        return 1  # below default threshold of 5

    with (
        patch.object(triggers, "_last_successful_run_time", _fake_last),
        patch.object(triggers, "_count_mutations_since", _fake_count),
    ):
        result = await triggers.meaningful_change_since_last_run("briefing_generator", "product:platform")
    assert result is False


@pytest.mark.unit
async def test_meaningful_change_returns_true_when_no_prior_run():
    """First-ever invocation of an engine: trigger fires (no last-run timestamp)."""
    from core.engine.sentinel import triggers

    async def _fake_last(*a, **k):
        return None  # no prior successful run

    async def _fake_count(*a, **k):
        return 0

    with (
        patch.object(triggers, "_last_successful_run_time", _fake_last),
        patch.object(triggers, "_count_mutations_since", _fake_count),
    ):
        result = await triggers.meaningful_change_since_last_run("briefing_generator", "product:platform")
    assert result is True


@pytest.mark.unit
async def test_meaningful_change_fails_open_on_db_error():
    """If the DB query raises, trigger returns True (fail-open — never silently skip)."""
    from core.engine.sentinel import triggers

    async def _raises(*a, **k):
        raise RuntimeError("db unavailable")

    with patch.object(triggers, "_last_successful_run_time", _raises):
        result = await triggers.meaningful_change_since_last_run("briefing_generator", "product:platform")
    assert result is True


@pytest.mark.unit
async def test_unread_signals_threshold():
    from core.engine.sentinel import triggers

    async def _fake_count(*a, **k):
        return 12

    with patch.object(triggers, "_count_unread_signals", _fake_count):
        assert await triggers.unread_signals_threshold(threshold=10, product_id="product:platform") is True
        assert await triggers.unread_signals_threshold(threshold=15, product_id="product:platform") is False
