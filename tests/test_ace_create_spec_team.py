"""ace_create_spec routes the human source to the deep-committee build path."""

import pytest

from core.engine.mcp import tools as mcp_tools


def _ret(v):
    async def f(*a, **k):
        return v

    return f


class _FakeGen:
    def __init__(self, *a, **k):
        self.calls: list[str] = []

    async def from_request_with_team(self, description, product_id, event_callback=None):
        self.calls.append("team")
        return {"objective": description, "authored_by": "build_team"}

    async def from_request(self, description, product_id):
        self.calls.append("solo")
        return {"objective": description, "authored_by": "solo"}

    async def from_gap(self, gap, capability_slug, product_id):
        self.calls.append("gap")
        return {"objective": "gap path"}


@pytest.mark.integration
async def test_ace_create_spec_human_routes_to_team(monkeypatch):
    """source='human' (default) must convene the build partner team, not the solo path."""
    instances: list[_FakeGen] = []

    def _factory(pool):
        gen = _FakeGen()
        instances.append(gen)
        return gen

    monkeypatch.setattr("core.engine.product.spec_generator.SpecGenerator", _factory)

    out = await mcp_tools.ace_create_spec("redesign the importer", source="human")
    assert out["authored_by"] == "build_team"
    assert instances and instances[0].calls == ["team"]


@pytest.mark.integration
async def test_ace_create_spec_gap_still_routes_to_from_gap(monkeypatch):
    """source='gap' is unchanged — still goes through from_gap."""
    instances: list[_FakeGen] = []

    def _factory(pool):
        gen = _FakeGen()
        instances.append(gen)
        return gen

    monkeypatch.setattr("core.engine.product.spec_generator.SpecGenerator", _factory)

    out = await mcp_tools.ace_create_spec("quality gap text", source="gap", capability_slug="my-cap")
    assert instances and instances[0].calls == ["gap"]
