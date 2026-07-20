"""A failed insight write must be OBSERVABLE, not silent.

Regression guard for the session's recurring failure class (the Phase-1 RELATE
bug got silently swallowed by the per-insight capture guard). _write_new_insights
must: count failures, increment the ace_capture_write_failures_total metric, and
still write the rest of the batch.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.capture.synthesizer import Synthesizer
from core.engine.core.metrics import capture_write_failures_total


def _metric_value(product: str) -> float:
    return capture_write_failures_total.labels(product=product)._value.get()


@pytest.mark.asyncio
async def test_one_failure_counted_metered_and_batch_continues():
    s = Synthesizer.__new__(Synthesizer)
    s.product_id = "product:test_obs_77731"
    s._db_pool = object()

    calls = {"n": 0}

    async def flaky_write(insight_data, observation_ids=None, provenance_kind=None):
        calls["n"] += 1
        if insight_data["content"] == "boom":
            raise RuntimeError("atomic write failed (rolled back)")

    s._write_insight = flaky_write  # instance attr -> no self binding
    before = _metric_value("product:test_obs_77731")

    with patch("core.engine.events.bus.bus.emit", new=AsyncMock()) as emit:
        written, failures, _records = await s._write_new_insights(
            [
                {"content": "ok-1", "domain_path": "test"},
                {"content": "boom", "domain_path": "test"},
                {"content": "ok-2", "domain_path": "test"},
            ],
            fallback_domain="test",
            batch_obs_ids=[],
        )

    # the batch continued past the failure: 2 written, 1 failed (all 3 attempted)
    assert (written, failures) == (2, 1)
    assert calls["n"] == 3
    # the failure is metered (not silent)
    assert _metric_value("product:test_obs_77731") == before + 1
    # and an observable event is emitted
    emit.assert_awaited_once()
    assert emit.await_args.args[0] == "capture.write_failed"
    assert emit.await_args.args[1]["count"] == 1


@pytest.mark.asyncio
async def test_no_failures_no_event_no_metric_change():
    s = Synthesizer.__new__(Synthesizer)
    s.product_id = "product:test_obs_77732"
    s._db_pool = object()

    async def ok_write(insight_data, observation_ids=None, provenance_kind=None):
        return None

    s._write_insight = ok_write  # instance attr -> no self binding
    before = _metric_value("product:test_obs_77732")
    with patch("core.engine.events.bus.bus.emit", new=AsyncMock()) as emit:
        written, failures, _records = await s._write_new_insights(
            [{"content": "ok", "domain_path": "test"}], fallback_domain="test", batch_obs_ids=[]
        )

    assert (written, failures) == (1, 0)
    assert _metric_value("product:test_obs_77732") == before  # unchanged
    emit.assert_not_awaited()
