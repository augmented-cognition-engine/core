"""MoA Part 1 — cross-model proposal routing.

`propose`/`aggregate` must route each model to the RIGHT provider: claude-* to the brain provider
(get_llm, normally the Claude CLI), non-claude models to a LOCAL Ollama peer (settings.moa_peer_host)
built directly. Today they resolve ONE get_llm() for every model, so non-claude proposers fail and
drop — MoA is single-vendor (correlated proposals). Enabling the peer must NOT flip the global brain to
Ollama. See docs/superpowers/specs/2026-06-23-moa-cross-model-routing-design.md.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel


class _Tiny(BaseModel):
    answer: str


class _RecordingProvider:
    """Stand-in provider: records the model it was called with, returns a valid schema instance."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def complete_structured(self, prompt, schema, model=None, max_tokens=2048):
        self.calls.append(model)
        return schema(answer=f"ok:{model}")


class _BoomProvider:
    async def complete_structured(self, *a, **k):
        raise RuntimeError("provider down")


# ── routing helper (_provider_for) ────────────────────────────────────────────


def test_provider_for_claude_model_uses_get_llm(monkeypatch):
    """A claude-* model always routes to get_llm() — even when a local peer IS configured."""
    import core.engine.cognition.moa as moa
    import core.engine.core.config as cfg

    monkeypatch.setattr(cfg.settings, "moa_peer_host", "http://localhost:11434", raising=False)
    sentinel = object()
    monkeypatch.setattr(moa, "get_llm", lambda: sentinel)
    assert moa._provider_for("claude-haiku-4-5-20251001") is sentinel


def test_provider_for_local_model_uses_ollama_peer_when_configured(monkeypatch):
    """A non-claude model + moa_peer_host set → OllamaProvider on that host with default_model == model."""
    import core.engine.cognition.moa as moa
    import core.engine.core.config as cfg
    from core.engine.core.llm import OllamaProvider

    monkeypatch.setattr(cfg.settings, "moa_peer_host", "http://localhost:11434", raising=False)
    p = moa._provider_for("qwen2.5-coder:14b")
    assert isinstance(p, OllamaProvider)
    assert p._default_model == "qwen2.5-coder:14b"
    assert p._host == "http://localhost:11434"


def test_provider_for_local_model_without_peer_falls_back_to_get_llm(monkeypatch):
    """No peer configured → get_llm() (the non-claude model then fails and drops, exactly as today)."""
    import core.engine.cognition.moa as moa
    import core.engine.core.config as cfg

    monkeypatch.setattr(cfg.settings, "moa_peer_host", None, raising=False)
    sentinel = object()
    monkeypatch.setattr(moa, "get_llm", lambda: sentinel)
    assert moa._provider_for("qwen2.5-coder:14b") is sentinel


def test_provider_for_uses_moa_peer_host_not_global_ollama_host(monkeypatch):
    """The peer host must come from moa_peer_host, NOT the global ollama_host (which routes the whole
    brain). Set them to DIFFERENT values and prove the provider binds to the MoA-dedicated one — and
    that resolving a peer never mutates the global ollama_host."""
    import core.engine.cognition.moa as moa
    import core.engine.core.config as cfg
    from core.engine.core.llm import OllamaProvider

    monkeypatch.setattr(cfg.settings, "ollama_host", "http://brain-do-not-use:11434", raising=False)
    monkeypatch.setattr(cfg.settings, "moa_peer_host", "http://moa-peer:11434", raising=False)
    p = moa._provider_for("qwen2.5-coder:14b")
    assert isinstance(p, OllamaProvider)
    assert p._host == "http://moa-peer:11434", "peer must bind to moa_peer_host, never the global brain host"
    assert cfg.settings.ollama_host == "http://brain-do-not-use:11434", "resolving a peer must not mutate ollama_host"


# ── propose / aggregate wiring ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_propose_routes_each_model(monkeypatch):
    """propose() routes EVERY model through _provider_for and returns one Proposal per success."""
    import core.engine.cognition.moa as moa

    seen: dict[str, _RecordingProvider] = {}

    def fake_provider_for(model: str):
        p = _RecordingProvider()
        seen[model] = p
        return p

    monkeypatch.setattr(moa, "_provider_for", fake_provider_for)
    proposals = await moa.propose("task", _Tiny, models=["claude-haiku-4-5-20251001", "qwen2.5-coder:14b"])

    assert set(seen) == {"claude-haiku-4-5-20251001", "qwen2.5-coder:14b"}, "both models must be routed"
    assert {p.model for p in proposals} == {"claude-haiku-4-5-20251001", "qwen2.5-coder:14b"}
    assert all(p.raw for p in proposals), "each Proposal carries its raw JSON"


@pytest.mark.asyncio
async def test_propose_drops_failed_proposer(monkeypatch):
    """A proposer whose provider raises is dropped non-fatally; the surviving one is returned."""
    import core.engine.cognition.moa as moa

    def fake_provider_for(model: str):
        return _BoomProvider() if model == "boom" else _RecordingProvider()

    monkeypatch.setattr(moa, "_provider_for", fake_provider_for)
    proposals = await moa.propose("task", _Tiny, models=["claude-haiku-4-5-20251001", "boom"])
    assert {p.model for p in proposals} == {"claude-haiku-4-5-20251001"}


@pytest.mark.asyncio
async def test_aggregate_routes_aggregator_model(monkeypatch):
    """aggregate() routes the aggregator_model through _provider_for and tags the result with it."""
    import core.engine.cognition.moa as moa

    seen: dict[str, _RecordingProvider] = {}

    def fake_provider_for(model: str):
        p = _RecordingProvider()
        seen[model] = p
        return p

    monkeypatch.setattr(moa, "_provider_for", fake_provider_for)
    props = [moa.Proposal(model="qwen2.5-coder:14b", output=_Tiny(answer="a"), raw=_Tiny(answer="a").model_dump_json())]
    agg = await moa.aggregate(props, task="t", schema=_Tiny, aggregator_model="claude-opus-4-6")

    assert agg is not None
    assert agg.model == "claude-opus-4-6"
    assert "claude-opus-4-6" in seen, "aggregator must be routed via _provider_for"


@pytest.mark.asyncio
async def test_aggregate_empty_proposals_returns_none(monkeypatch):
    """No proposals → None (unchanged contract; nothing to synthesize)."""
    import core.engine.cognition.moa as moa

    agg = await moa.aggregate([], task="t", schema=_Tiny, aggregator_model="claude-opus-4-6")
    assert agg is None
