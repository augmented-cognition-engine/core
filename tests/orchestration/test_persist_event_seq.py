import pytest

import core.engine.orchestration.events as ev


@pytest.mark.asyncio
async def test_persist_event_writes_seq(monkeypatch):
    captured = {}

    class _DB:
        async def query(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params or {}
            return [[{}]]

    class _CM:
        async def __aenter__(self):
            return _DB()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def connection(self):
            return _CM()

    monkeypatch.setattr("core.engine.core.db.pool", _Pool())

    await ev._persist_event(
        {"run_id": "r1", "task_id": "t1", "type": "block_start", "seq": 7, "block_name": "classify"}
    )

    assert captured["params"]["seq"] == 7
    assert "seq = $seq" in captured["sql"]
    # seq is a top-level column, not buried in payload
    assert "seq" not in captured["params"]["payload"]
