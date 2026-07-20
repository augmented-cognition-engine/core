"""The session must be reachable, or it is an elaborate module nobody can run."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_build_session_tool_delegates_and_reports(monkeypatch):
    import core.engine.arms.session as session
    from core.engine.mcp.tools import ace_build_session

    async def _run(product_id="product:platform", max_builds=5, pool=None):
        return {
            "built": [{"spec": "agent_spec:a", "branch": "arm/code-1"}],
            "failed": [],
            "reconciled_zombies": 0,
            "stopped_because": "no work left",
            "diagnosis": "",
            "needs_human": False,
        }

    monkeypatch.setattr(session, "run_build_session", _run)

    out = await ace_build_session(product_id="product:platform", max_builds=5)

    assert out["stopped_because"] == "no work left"
    assert len(out["built"]) == 1


@pytest.mark.asyncio
async def test_build_session_tool_is_fail_safe(monkeypatch):
    import core.engine.arms.session as session
    from core.engine.mcp.tools import ace_build_session

    async def _boom(**kw):
        raise RuntimeError("db gone")

    monkeypatch.setattr(session, "run_build_session", _boom)

    out = await ace_build_session(product_id="product:platform")

    assert out["needs_human"] is True
    assert out["stopped_because"] == "error"


def test_build_session_is_registered_on_the_mcp_server():
    import inspect

    import core.engine.mcp.server as server

    src = inspect.getsource(server)
    assert "async def ace_build_session" in src
    idx = src.index("async def ace_build_session")
    preceding = src[:idx].rstrip().splitlines()[-1]
    assert "@mcp.tool" in preceding, "an unregistered session tool is unreachable in production"
