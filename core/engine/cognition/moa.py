# engine/cognition/moa.py
"""Mixture-of-Agents primitives: diverse multi-model proposal + synthesis.

Unlike self_consistency (same model N times → correlated samples), MoA samples
from DIFFERENT models (uncorrelated failure modes) and synthesizes their
proposals with an aggregator pass. Schema-generic; the executor passes PhaseOutput.

Both functions are non-fatal: a failed proposer or aggregator is dropped/None,
never raised — mirroring self_consistency.sample_structured.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from core.engine.core.llm import get_llm

if TYPE_CHECKING:
    from core.engine.core.llm import LLMProvider

logger = logging.getLogger(__name__)

__all__ = ["Proposal", "propose", "aggregate"]

T = TypeVar("T", bound=BaseModel)


def _provider_for(model: str) -> "LLMProvider":
    """Route a proposer/aggregator model to its provider — the unblock for cross-model MoA.

    claude-* → the configured brain provider (get_llm(), normally the Claude CLI).
    non-claude → a LOCAL Ollama peer (settings.moa_peer_host), built DIRECTLY — never via
    get_llm()/ollama_host, so MoA's cross-model proposers never flip the brain to Ollama (get_llm reads
    ollama_host as a global switch; MoA must not trip it). No peer configured → get_llm() (the
    non-claude model then fails and drops non-fatally in propose's _one, exactly as before this change).

    OllamaProvider(default_model=model) is safe: _resolve_model passes a real (non-claude, unmapped)
    Ollama name through as-is, and a degenerate name collapses to default_model == model either way.
    """
    if not model.startswith("claude"):
        from core.engine.core.config import settings

        host = getattr(settings, "moa_peer_host", None)
        if host:
            from core.engine.core.llm import OllamaProvider

            return OllamaProvider(host=host, default_model=model)
    return get_llm()


@dataclass(frozen=True)
class Proposal:
    """One model's structured proposal for a phase.

    raw is output.model_dump_json() — the JSON string downstream code (the
    executor) parses back into its own schema (e.g. PhaseOutput).
    """

    model: str
    output: BaseModel
    raw: str


async def propose(
    prompt: str,
    schema: type[T],
    models: list[str],
    max_tokens: int = 2048,
) -> list[Proposal]:
    """Generate one structured proposal per model, in parallel. Drops failures.

    Never raises; returns [] if every model fails.
    """

    async def _one(model: str) -> Proposal | None:
        try:
            provider = _provider_for(model)
            out = await provider.complete_structured(prompt, schema=schema, model=model, max_tokens=max_tokens)
            return Proposal(model=model, output=out, raw=out.model_dump_json())
        except Exception as exc:
            logger.debug("MoA proposer %s failed (non-fatal): %s", model, exc)
            return None

    results = await asyncio.gather(*[_one(m) for m in models])
    return [r for r in results if r is not None]


def _synthesis_prompt(proposals: list[Proposal], task: str) -> str:
    blocks = []
    for i, p in enumerate(proposals, 1):
        blocks.append(f"### Expert {i} ({p.model})\n{p.raw}")
    joined = "\n\n".join(blocks)
    return (
        f"Task:\n{task}\n\n"
        f"{len(proposals)} independent expert analyses of this task are below. "
        f"Synthesize the single best answer: reconcile their disagreements, keep each one's "
        f"strongest insight, and discard what is weak or wrong. Do not merely pick one — combine them.\n\n"
        f"{joined}"
    )


async def aggregate(
    proposals: list[Proposal],
    task: str,
    schema: type[T],
    aggregator_model: str,
    max_tokens: int = 2048,
) -> Proposal | None:
    """Synthesize proposals into one refined output via the aggregator model.

    Returns the aggregate as a Proposal (model=aggregator_model), or None when
    there are no proposals or the aggregator call fails (non-fatal).
    """
    if not proposals:
        return None
    try:
        llm = _provider_for(aggregator_model)
        out = await llm.complete_structured(
            _synthesis_prompt(proposals, task), schema=schema, model=aggregator_model, max_tokens=max_tokens
        )
        return Proposal(model=aggregator_model, output=out, raw=out.model_dump_json())
    except Exception as exc:
        logger.debug("MoA aggregate failed (non-fatal): %s", exc)
        return None
