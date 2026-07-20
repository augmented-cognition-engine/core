"""overthinking_observer aggregates flagged composition_signal rows daily."""

import pytest


@pytest.mark.integration
async def test_observer_emits_insight_when_threshold_exceeded(monkeypatch):
    """When ≥10 overthinking events for a (discipline, model) pair occur in
    a 14-day window, the observer emits an ace-insight row."""
    from core.engine.sentinel.engines import overthinking_observer as obs

    insight_inserts: list[dict] = []

    class _FakeDB:
        async def query(self, q, params=None):
            if "GROUP BY discipline, model_used" in q:
                return [
                    {
                        "result": [
                            {
                                "discipline": "architecture",
                                "model_used": "claude-haiku-4-5-20251001",
                                "n": 23,
                                "total_cost": 4.20,
                                "total_alt_cost": 1.15,
                            }
                        ]
                    }
                ]
            if "CREATE ace_insight" in q:
                insight_inserts.append(params or {})
                return [{"result": [{"id": "ace_insight:fake"}]}]
            return []

    class _FakeConn:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *exc):
            return False

    class _FakePool:
        def connection(self):
            return _FakeConn()

    monkeypatch.setattr(obs, "pool", _FakePool())
    result = await obs.run_overthinking_observer("product:platform")

    assert result["status"] == "completed"
    assert len(insight_inserts) == 1
    p = insight_inserts[0]
    assert "architecture" in p["content"]
    assert "claude-haiku-4-5-20251001" in p["content"]
    assert "23" in p["content"]


@pytest.mark.integration
async def test_observer_emits_no_insight_below_threshold(monkeypatch):
    """When the aggregate shows fewer than 10 events, no insight is emitted."""
    from core.engine.sentinel.engines import overthinking_observer as obs

    insight_inserts: list[dict] = []

    class _FakeDB:
        async def query(self, q, params=None):
            if "GROUP BY discipline, model_used" in q:
                return [
                    {
                        "result": [
                            {
                                "discipline": "testing",
                                "model_used": "claude-haiku-4-5-20251001",
                                "n": 3,
                                "total_cost": 0.10,
                                "total_alt_cost": 0.05,
                            }
                        ]
                    }
                ]
            if "CREATE ace_insight" in q:
                insight_inserts.append(params or {})
                return [{"result": [{"id": "ace_insight:fake"}]}]
            return []

    class _FakeConn:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *exc):
            return False

    class _FakePool:
        def connection(self):
            return _FakeConn()

    monkeypatch.setattr(obs, "pool", _FakePool())
    result = await obs.run_overthinking_observer("product:platform")

    assert result["status"] == "completed"
    assert insight_inserts == []
