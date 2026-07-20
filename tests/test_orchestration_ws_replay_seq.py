# tests/test_orchestration_ws_replay_seq.py
import pytest

import core.engine.api.orchestration_ws as ows


class _WS:
    def __init__(self):
        self.sent = []

    async def send_json(self, d):
        self.sent.append(d)


@pytest.mark.asyncio
async def test_replay_uses_seq_cursor(monkeypatch):
    captured = {}

    class _DB:
        async def query(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params or {}
            return [
                [
                    {
                        "type": "token",
                        "run_id": "r1",
                        "task_id": "canvas-perspective-0",
                        "seq": 6,
                        # stray payload "seq" must NOT override the top-level column —
                        # a corrupted seq would break the very cursor this feature relies on.
                        "payload": {"delta": "x", "seq": 999},
                    },
                ]
            ]

    class _CM:
        async def __aenter__(self):
            return _DB()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def connection(self):
            return _CM()

    monkeypatch.setattr(ows, "default_pool", _Pool())

    ws = _WS()
    await ows._replay(ws, run_id="r1", last_seq=5)

    assert "seq > $last_seq" in captured["sql"]
    assert "ORDER BY seq" in captured["sql"]
    assert captured["params"]["last_seq"] == 5
    types = [m.get("type") for m in ws.sent]
    assert "replay_start" in types and "replay_done" in types
    # the replayed event carries its seq so the client can advance its cursor;
    # the explicit column (6) wins over a colliding payload key (999).
    replayed = [m for m in ws.sent if m.get("type") == "token"]
    assert replayed and replayed[0]["seq"] == 6
    assert replayed[0]["delta"] == "x"
