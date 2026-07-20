from __future__ import annotations

import pytest

import core.engine.product.discover as disc


class _LLM:
    def __init__(self, payload):
        self._payload = payload

    async def complete_json(self, prompt):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.mark.asyncio
async def test_fanout_returns_n_directions():
    llm = _LLM({"directions": ["a", "b", "c", "d", "e"]})
    out = await disc._fanout_directions("vision", {}, 4, llm=llm)
    assert out == ["a", "b", "c", "d"]  # capped at n


@pytest.mark.asyncio
async def test_fanout_degrades_to_vision_on_error():
    llm = _LLM(RuntimeError("down"))
    out = await disc._fanout_directions("the vision text", {}, 4, llm=llm)
    assert out == ["the vision text"]


@pytest.mark.asyncio
async def test_converge_picks_top_k_by_index():
    llm = _LLM({"top": [1, 3]})
    out = await disc._converge("v", ["d1", "d2", "d3", "d4"], 2, llm=llm)
    assert out == ["d1", "d3"]


@pytest.mark.asyncio
async def test_converge_passthrough_when_few():
    llm = _LLM({"top": []})
    out = await disc._converge("v", ["only", "two"], 2, llm=llm)
    assert out == ["only", "two"]  # <= k -> no LLM call needed


@pytest.mark.asyncio
async def test_converge_degrades_to_first_k_on_error():
    llm = _LLM(RuntimeError("down"))
    out = await disc._converge("v", ["d1", "d2", "d3"], 2, llm=llm)
    assert out == ["d1", "d2"]


@pytest.mark.asyncio
async def test_fanout_dedups_near_identical_framings():
    llm = _LLM({"directions": ["Make it alive", "make it ALIVE", "make  it  alive", "A distinct one"]})
    out = await disc._fanout_directions("v", {}, 4, llm=llm)
    assert out == ["Make it alive", "A distinct one"]  # case/space-normalized dedup


class _Gen:
    def __init__(self):
        self.calls = []

    async def from_request(self, request, product_id, source="human"):
        self.calls.append((request, source))
        return {"id": f"agent_spec:{len(self.calls)}", "objective": request, "status": "draft"}


@pytest.mark.asyncio
async def test_discover_emits_k_candidate_specs_tagged_discover():
    class _Router:
        async def complete_json(self, prompt):
            if "Propose" in prompt:
                return {"directions": ["d1", "d2", "d3", "d4"]}
            return {"top": [1, 2]}

    gen = _Gen()
    out = await disc.discover("a vision", "product:platform", n_directions=4, top_k=2, generator=gen, llm=_Router())
    assert len(out["candidates"]) == 2
    # emitted the top-2 directions, each tagged source='discover' (filterable from deliberate specs)
    assert gen.calls == [("d1", "discover"), ("d2", "discover")]
    assert all(c["id"].startswith("agent_spec:") for c in out["candidates"])


@pytest.mark.asyncio
async def test_discover_skips_a_failed_emission():
    class _Router:
        async def complete_json(self, prompt):
            if "Propose" in prompt:
                return {"directions": ["good", "bad"]}
            return {"top": [1, 2]}

    class _PartialGen:
        async def from_request(self, request, product_id, source="human"):
            if request == "bad":
                raise RuntimeError("spec gen failed")
            return {"id": "agent_spec:ok", "objective": request}

    out = await disc.discover("v", "product:platform", n_directions=2, top_k=2, generator=_PartialGen(), llm=_Router())
    assert len(out["candidates"]) == 1 and out["candidates"][0]["objective"] == "good"


@pytest.mark.asyncio
async def test_ace_discover_tool_delegates(monkeypatch):
    from core.engine.mcp import tools

    async def fake_discover(vision, product_id="product:platform", **kw):
        return {"candidates": [{"id": "agent_spec:x", "objective": vision}], "directions_considered": [vision]}

    monkeypatch.setattr("core.engine.product.discover.discover", fake_discover)
    out = await tools.ace_discover("make onboarding feel alive")
    assert out["candidates"][0]["objective"] == "make onboarding feel alive"


@pytest.mark.asyncio
async def test_ace_discover_is_registered_as_mcp_tool():
    # Reachability guard: defining ace_discover in tools.py is NOT enough — it must be registered
    # on the MCP server (@mcp.tool in server.py) to be invocable in production. This test would
    # have caught the orphan-tool bug.
    from core.engine.mcp.server import mcp

    names = {t.name for t in await mcp.list_tools()}
    assert "ace_discover" in names, sorted(names)
