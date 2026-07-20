"""composition_signal_hook captures cost-aware fields (Phase A spec §F)."""

from unittest.mock import MagicMock

import pytest


class _Acc:
    """Token accumulator stub."""

    def __init__(self, ti, to):
        self._ti, self._to = ti, to

    def total_input(self):
        return self._ti

    def total_output(self):
        return self._to

    def total(self):
        return self._ti + self._to


@pytest.mark.integration
async def test_hook_writes_cost_usd_for_haiku_run(monkeypatch):
    """For a Haiku-model run with 1000 in / 500 out tokens, cost_usd ≈ 0.0028
    and estimated_alternative_cost_usd ≈ 0.007 (Sonnet on same volume)."""
    from core.engine.orchestration import hooks

    captured_params: list[dict] = []

    class _FakeDB:
        async def query(self, q, params=None):
            captured_params.append(params or {})
            return [{"result": [{"id": "composition_signal:fake"}]}]

    class _FakeConn:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *exc):
            return False

    class _FakePool:
        def connection(self):
            return _FakeConn()

    monkeypatch.setattr(hooks, "pool", _FakePool())

    async def _fake_baseline(*a, **k):
        return None

    monkeypatch.setattr(hooks, "estimate_baseline", _fake_baseline)

    ctx = MagicMock()
    ctx.classification = {
        "discipline": "architecture",
        "complexity": "simple",
        "mode": "reactive",
        "engagement": {"perspectives": ["practitioner"]},
        "perspective_weights": {"practitioner": 1.0},
        "token_budget": 1024,
        "mode_confidence": 0.9,
    }
    ctx.task_id = "task:fake"
    ctx.product_id = "product:platform"
    ctx.token_accumulator = _Acc(1000, 500)
    ctx.engagement_result = {"engagement_type": "single", "spin_count": 1}
    ctx.snapshot = {"intelligence_utilization": {"utilization_rate": 0.5}}
    ctx.phase_traces = [{"confidence": 0.9}]
    ctx.frameworks_used = ["first-principles"]
    ctx.model_used = "claude-haiku-4-5-20251001"
    ctx.call_count_used = 1
    ctx.call_budget_estimated = 4

    await hooks.composition_signal_hook(ctx)

    assert captured_params, "hook should have written a row"
    p = captured_params[0]
    assert p["model_used"] == "claude-haiku-4-5-20251001"
    assert p["budget_estimated"] == 1024
    assert p["budget_used"] == 500
    assert abs(p["cost_usd"] - 0.0028) < 1e-6
    assert abs(p["estimated_alternative_cost_usd"] - 0.007) < 1e-6
    # ratio 500/1000 = 0.5, not > 5 → not overthinking
    assert p["overthinking_flag"] is False


@pytest.mark.integration
async def test_hook_writes_call_budget_fields(monkeypatch):
    """call_count_used and call_budget_estimated flow from ctx to the row."""
    from core.engine.orchestration import hooks

    captured: list[dict] = []

    class _FakeDB:
        async def query(self, q, params=None):
            captured.append(params or {})
            return [{"result": [{"id": "composition_signal:fake"}]}]

    class _FakeConn:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *exc):
            return False

    class _FakePool:
        def connection(self):
            return _FakeConn()

    monkeypatch.setattr(hooks, "pool", _FakePool())

    async def _fake_baseline(*a, **k):
        return None

    monkeypatch.setattr(hooks, "estimate_baseline", _fake_baseline)

    ctx = MagicMock()
    ctx.classification = {
        "discipline": "x",
        "complexity": "complex",
        "mode": "deliberative",
        "engagement": {"perspectives": ["theorist"]},
        "perspective_weights": {"theorist": 1.0},
        "token_budget": 6144,
    }
    ctx.task_id = "task:fake"
    ctx.product_id = "product:platform"
    ctx.token_accumulator = _Acc(2000, 4000)
    ctx.engagement_result = {"engagement_type": "single", "spin_count": 1}
    ctx.snapshot = {}
    ctx.phase_traces = []
    ctx.frameworks_used = []
    ctx.model_used = "claude-sonnet-4-6"
    ctx.call_count_used = 12
    ctx.call_budget_estimated = 16

    await hooks.composition_signal_hook(ctx)
    p = captured[0]
    assert p["call_count_used"] == 12
    assert p["call_budget_estimated"] == 16
    assert p["model_used"] == "claude-sonnet-4-6"


@pytest.mark.integration
async def test_hook_handles_missing_optional_ctx_attrs(monkeypatch):
    """When ctx lacks model_used / call_count_used (legacy callers), hook still
    writes a row with those fields as None — does not raise."""
    from core.engine.orchestration import hooks

    captured: list[dict] = []

    class _FakeDB:
        async def query(self, q, params=None):
            captured.append(params or {})
            return [{"result": [{"id": "composition_signal:fake"}]}]

    class _FakeConn:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *exc):
            return False

    class _FakePool:
        def connection(self):
            return _FakeConn()

    monkeypatch.setattr(hooks, "pool", _FakePool())

    async def _fake_baseline(*a, **k):
        return None

    monkeypatch.setattr(hooks, "estimate_baseline", _fake_baseline)

    # Bare class — none of the new attrs exist as real values
    class _BareCtx:
        classification = {
            "discipline": "x",
            "complexity": "moderate",
            "mode": "reactive",
            "engagement": {"perspectives": ["practitioner"]},
            "perspective_weights": {"practitioner": 1.0},
        }
        task_id = "task:fake"
        product_id = "product:platform"
        token_accumulator = _Acc(0, 0)
        engagement_result = {}
        snapshot = {}
        phase_traces = []
        frameworks_used = []
        # NO model_used, call_count_used, call_budget_estimated attrs

    await hooks.composition_signal_hook(_BareCtx())
    p = captured[0]
    assert p["model_used"] is None
    assert p["call_count_used"] is None
    assert p["call_budget_estimated"] is None
    assert p["cost_usd"] is None  # no model → no cost
