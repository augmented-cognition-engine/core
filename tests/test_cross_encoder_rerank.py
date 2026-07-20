"""Cross-encoder rerank — a final relevance pass over ace_search's RRF candidates via the local Ollama
peer (LLM-as-reranker, no API). Gated + fail-open: off / error → original RRF order. See
docs/superpowers/specs/2026-06-23-cross-encoder-rerank-design.md.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

_CANDS = [
    {"id": "insight:a", "content": "alpha", "score": 0.9},
    {"id": "insight:b", "content": "bravo", "score": 0.8},
    {"id": "insight:c", "content": "charlie", "score": 0.7},
]


class _FakeProvider:
    def __init__(self, order):
        self._order = order

    async def complete_json(self, prompt, model=None, **kw):
        return {"order": self._order}


@pytest.mark.asyncio
async def test_disabled_returns_original_order(monkeypatch):
    """No rerank_peer_host → no-op: original order, no provider constructed."""
    import core.engine.core.config as cfg
    from core.engine.search import rerank

    monkeypatch.setattr(cfg.settings, "rerank_peer_host", None, raising=False)
    with patch.object(rerank, "OllamaProvider") as mp:
        out = await rerank.cross_encoder_rerank("q", _CANDS, top_k=10)
    assert [c["id"] for c in out] == ["insight:a", "insight:b", "insight:c"]
    mp.assert_not_called()


@pytest.mark.asyncio
async def test_reorders_by_model_ranking(monkeypatch):
    import core.engine.core.config as cfg
    from core.engine.search import rerank

    monkeypatch.setattr(cfg.settings, "rerank_peer_host", "http://localhost:11434", raising=False)
    with patch.object(rerank, "OllamaProvider", return_value=_FakeProvider([2, 0, 1])):
        out = await rerank.cross_encoder_rerank("q", _CANDS, top_k=10)
    assert [c["id"] for c in out] == ["insight:c", "insight:a", "insight:b"]


@pytest.mark.asyncio
async def test_omitted_index_is_appended_not_dropped(monkeypatch):
    import core.engine.core.config as cfg
    from core.engine.search import rerank

    monkeypatch.setattr(cfg.settings, "rerank_peer_host", "http://localhost:11434", raising=False)
    with patch.object(rerank, "OllamaProvider", return_value=_FakeProvider([2, 0])):  # omits index 1
        out = await rerank.cross_encoder_rerank("q", _CANDS, top_k=10)
    assert [c["id"] for c in out] == ["insight:c", "insight:a", "insight:b"]  # b appended, not dropped


@pytest.mark.asyncio
async def test_out_of_range_and_nonint_indices_ignored(monkeypatch):
    import core.engine.core.config as cfg
    from core.engine.search import rerank

    monkeypatch.setattr(cfg.settings, "rerank_peer_host", "http://localhost:11434", raising=False)
    with patch.object(rerank, "OllamaProvider", return_value=_FakeProvider([9, "x", 1, 0])):
        out = await rerank.cross_encoder_rerank("q", _CANDS, top_k=10)
    # 9 and "x" ignored; 1,0 honored; 2 appended
    assert [c["id"] for c in out] == ["insight:b", "insight:a", "insight:c"]


@pytest.mark.asyncio
async def test_fail_open_on_provider_error(monkeypatch):
    import core.engine.core.config as cfg
    from core.engine.search import rerank

    class _Boom:
        async def complete_json(self, *a, **k):
            raise RuntimeError("ollama down")

    monkeypatch.setattr(cfg.settings, "rerank_peer_host", "http://localhost:11434", raising=False)
    with patch.object(rerank, "OllamaProvider", return_value=_Boom()):
        out = await rerank.cross_encoder_rerank("q", _CANDS, top_k=10)
    assert [c["id"] for c in out] == ["insight:a", "insight:b", "insight:c"]  # original order


@pytest.mark.asyncio
async def test_top_k_caps_after_rerank(monkeypatch):
    import core.engine.core.config as cfg
    from core.engine.search import rerank

    monkeypatch.setattr(cfg.settings, "rerank_peer_host", "http://localhost:11434", raising=False)
    with patch.object(rerank, "OllamaProvider", return_value=_FakeProvider([2, 0, 1])):
        out = await rerank.cross_encoder_rerank("q", _CANDS, top_k=2)
    assert [c["id"] for c in out] == ["insight:c", "insight:a"]


@pytest.mark.asyncio
async def test_hung_peer_fails_open_fast(monkeypatch):
    """A HUNG peer (accepts socket, never responds) must fail open via the rerank timeout — NOT block
    ace_search for the 120s httpx read timeout (the local peer hangs under load)."""
    import asyncio

    import core.engine.core.config as cfg
    from core.engine.search import rerank

    class _Hang:
        async def complete_json(self, *a, **k):
            await asyncio.sleep(5)  # longer than the (monkeypatched-tiny) rerank timeout
            return {"order": [2, 1, 0]}

    monkeypatch.setattr(cfg.settings, "rerank_peer_host", "http://localhost:11434", raising=False)
    monkeypatch.setattr(rerank, "_RERANK_TIMEOUT_S", 0.05, raising=False)
    with patch.object(rerank, "OllamaProvider", return_value=_Hang()):
        out = await rerank.cross_encoder_rerank("q", _CANDS, top_k=10)
    assert [c["id"] for c in out] == ["insight:a", "insight:b", "insight:c"]  # original order (timed out)


@pytest.mark.asyncio
async def test_bool_indices_ignored(monkeypatch):
    """bool is an int subclass — True/False in `order` must not be treated as positions 1/0."""
    import core.engine.core.config as cfg
    from core.engine.search import rerank

    monkeypatch.setattr(cfg.settings, "rerank_peer_host", "http://localhost:11434", raising=False)
    with patch.object(rerank, "OllamaProvider", return_value=_FakeProvider([True, False, 2, 1, 0])):
        out = await rerank.cross_encoder_rerank("q", _CANDS, top_k=10)
    assert [c["id"] for c in out] == ["insight:c", "insight:b", "insight:a"]  # bools ignored; 2,1,0 honored


@pytest.mark.asyncio
async def test_single_candidate_is_noop(monkeypatch):
    import core.engine.core.config as cfg
    from core.engine.search import rerank

    monkeypatch.setattr(cfg.settings, "rerank_peer_host", "http://localhost:11434", raising=False)
    with patch.object(rerank, "OllamaProvider") as mp:
        out = await rerank.cross_encoder_rerank("q", _CANDS[:1], top_k=10)
    assert [c["id"] for c in out] == ["insight:a"]
    mp.assert_not_called()
