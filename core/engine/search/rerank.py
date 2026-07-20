"""Cross-encoder rerank — a final relevance pass over hybrid (BM25+vector+RRF) candidates.

RRF fuses two bi-encoder rankings (keyword + embedding) but never scores the query against a candidate's
content TOGETHER. This adds that cross-encoder pass via a LOCAL Ollama peer (LLM-as-reranker — no API, no
metering, no new model dependency; the candidates already carry `content`). Gated + fail-open: with no
peer configured, ≤1 candidate, or ANY error, the original RRF order is returned unchanged — reranking is
strictly a refinement, never a dependency.
"""

from __future__ import annotations

import asyncio
import logging

from core.engine.core.llm import OllamaProvider

logger = logging.getLogger(__name__)

_SNIPPET_LEN = 500
# A hung local peer must fail open in SECONDS, not block ace_search (interactive path) for the 120s
# httpx read timeout — the local Ollama peer is known to HANG under sustained load. A rerank that takes
# longer than this has already lost its latency budget vs. just returning the RRF order.
_RERANK_TIMEOUT_S = 8.0


async def cross_encoder_rerank(query: str, candidates: list[dict], *, top_k: int = 10) -> list[dict]:
    """Reorder `candidates` by cross-encoder relevance to `query` (local Ollama peer); fail-open.

    Returns `candidates[:top_k]` unchanged when reranking is off (`settings.rerank_peer_host` unset),
    there is nothing to reorder (≤1 candidate), or anything fails. Indices the model omits are appended
    in their original order (no silent drops); malformed/out-of-range indices are ignored.
    """
    from core.engine.core.config import settings

    host = getattr(settings, "rerank_peer_host", None)
    if not host or len(candidates) <= 1:
        return candidates[:top_k]

    try:
        model = getattr(settings, "rerank_model", "qwen2.5-coder:14b")
        provider = OllamaProvider(host=host, default_model=model)

        blocks = [f"[{i}] {str(c.get('content', ''))[:_SNIPPET_LEN]}" for i, c in enumerate(candidates)]
        prompt = (
            f"Query: {query}\n\n"
            f"Rank the {len(candidates)} passages below by relevance to the query, most relevant first. "
            f'Return JSON only: {{"order": [passage indices, most relevant first]}}.\n\n' + "\n\n".join(blocks)
        )
        # asyncio.TimeoutError is an Exception subclass → caught below → fail-open to RRF order.
        out = await asyncio.wait_for(provider.complete_json(prompt, model=model), timeout=_RERANK_TIMEOUT_S)
        order = out.get("order", []) if isinstance(out, dict) else []

        reranked: list[dict] = []
        seen: set[int] = set()
        for idx in order:
            if isinstance(idx, bool):  # bool is an int subclass — never a valid position
                continue
            if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
                reranked.append(candidates[idx])
                seen.add(idx)
        # append anything the model omitted, in original order — never silently drop a candidate
        for i, c in enumerate(candidates):
            if i not in seen:
                reranked.append(c)
        return reranked[:top_k]
    except Exception:
        logger.warning("cross_encoder_rerank failed (non-fatal); original RRF order", exc_info=True)
        return candidates[:top_k]
