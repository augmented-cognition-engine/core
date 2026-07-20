"""DISCOVER — the front of the build->ship loop. Turns a vague VISION into well-scoped spec
candidates: explore (fanout directions) -> converge (criteria rank) -> emit (SpecGenerator).
The same `explore` primitive the arms use, at the goal altitude, emitting specs not plans."""

from __future__ import annotations

import logging

from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)


async def _fanout_directions(vision: str, context: dict, n: int, *, llm) -> list[str]:
    """Fanout N distinct concrete directions the vision could take. Non-fatal -> [vision]."""
    try:
        prompt = (
            f'A product vision: "{vision}".\n'
            f"Propose {n} DISTINCT, CONCRETE directions this vision could take — each a different "
            "approach (not a rephrasing), one or two sentences, actionable enough to scope a spec. "
            'Reply STRICT JSON: {"directions": ["...", "..."]}.\n\n'
            f"PRODUCT CONTEXT: {context}"
        )
        data = await llm.complete_json(prompt)
        dirs = data.get("directions", []) if isinstance(data, dict) else []
        # Dedup near-identical framings (the prompt asks for distinct, but the LLM may not comply)
        # before they cost a real from_request LLM call + DB write each.
        seen: set[str] = set()
        unique: list[str] = []
        for d in dirs:
            s = str(d).strip()
            key = " ".join(s.lower().split())
            if s and key not in seen:
                seen.add(key)
                unique.append(s)
        return unique[:n] if unique else [vision]
    except Exception as exc:
        logger.warning("discover._fanout_directions failed (non-fatal): %s", exc)
        return [vision]


async def _converge(vision: str, directions: list[str], k: int, *, llm) -> list[str]:
    """Rank directions by impact x feasibility x alignment -> top k. Non-fatal -> first k."""
    if len(directions) <= k:
        return directions
    try:
        numbered = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(directions))
        prompt = (
            f'Vision: "{vision}".\nRank these directions by (impact x feasibility x alignment) '
            f"and return the BEST {k} as their 1-based indices. "
            'Reply STRICT JSON: {"top": [1, 3]}.\n\n' + numbered
        )
        data = await llm.complete_json(prompt)
        idx = data.get("top", []) if isinstance(data, dict) else []
        chosen: list[str] = []
        for i in idx:
            try:
                j = int(i) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= j < len(directions) and directions[j] not in chosen:
                chosen.append(directions[j])
        return chosen[:k] if chosen else directions[:k]
    except Exception as exc:
        logger.warning("discover._converge failed (non-fatal): %s", exc)
        return directions[:k]


async def discover(
    vision: str,
    product_id: str = "product:platform",
    *,
    n_directions: int = 4,
    top_k: int = 2,
    generator=None,
    llm=None,
) -> dict:
    """Vision -> K candidate draft specs. explore (fanout) -> converge -> emit (SpecGenerator)."""
    llm = llm or get_llm()
    if generator is None:
        from core.engine.core.db import pool
        from core.engine.product.spec_generator import SpecGenerator

        generator = SpecGenerator(pool)

    context: dict = {}
    try:
        from core.engine.core.db import pool
        from core.engine.product.map import ProductMap

        pm = ProductMap(pool)
        context = {"vision": await pm.get_vision(product_id), "health": await pm.health_summary(product_id)}
    except Exception as exc:
        logger.warning("discover: product context load failed (non-fatal): %s", exc)

    directions = await _fanout_directions(vision, context, n_directions, llm=llm)
    chosen = await _converge(vision, directions, top_k, llm=llm)

    candidates: list[dict] = []
    for direction in chosen:
        try:
            # Tag provenance so DISCOVER candidates are filterable from deliberate specs.
            spec = await generator.from_request(direction, product_id, source="discover")
            if isinstance(spec, dict) and spec.get("id"):
                candidates.append({"id": str(spec["id"]), "objective": spec.get("objective", direction)})
        except Exception as exc:
            logger.warning("discover: from_request failed for a direction (non-fatal): %s", exc)
    return {"candidates": candidates, "directions_considered": directions}
