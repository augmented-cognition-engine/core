"""Sentinel engine: Community Summarizer — GraphRAG community summaries for briefings.

Runs Louvain community detection (graph/cluster.py) over the cognify insight edges, LLM-summarizes the
largest communities (the recurring themes in accumulated knowledge), and writes one community_summary
row per community. The briefing surfaces them so the partner sees the SHAPE of what's been learned, not
just counts.

LLM-gated + bounded: top-N communities only (budget), each summary wrapped in asyncio.wait_for so a slow
Claude CLI can't hang the weekly run. Non-fatal throughout (a failed summary is skipped, never raised).
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_record_ids, parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import get_llm
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

_MIN_CLUSTER_NODES = 5
_MAX_MEMBERS_SAMPLED = 15


def _validate(product_id: str, budget: int) -> None:
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for community_summarizer: {product_id!r}")
    if not (1 <= budget <= 20):
        raise ValidationError(f"budget must be in [1, 20], got {budget}")


@register_engine(
    name="community_summarizer",
    cron="0 3 * * sat",  # Saturday 3am — before the Monday briefing
    description="GraphRAG community summaries for briefings — Louvain clusters → LLM theme summary (Sat 3am)",
)
async def run_community_summarizer(product_id: str = "product:platform", budget: int = 5) -> dict:
    """Detect knowledge communities and summarize the largest; replace prior summaries for the product."""
    _validate(product_id, budget)

    from core.engine.capture.cognify import EDGE_TYPES
    from core.engine.graph.cluster import build_graph, detect_clusters

    edges: list[dict] = []
    async with pool.connection() as db:
        for edge_type in EDGE_TYPES:
            rows = parse_rows(
                await db.query(
                    f"SELECT in, out FROM {edge_type} "
                    "WHERE source = 'cognify' AND in.product = <record>$product LIMIT 1000",
                    {"product": product_id},
                )
            )
            for r in rows:
                src, tgt = str(r.get("in", "")), str(r.get("out", ""))
                if src and tgt and src != tgt:
                    edges.append({"from": src, "to": tgt, "type": edge_type})

    if not edges:
        return {"summarized": 0, "reason": "no_cognify_edges"}

    clusters = detect_clusters(build_graph(edges), min_nodes=_MIN_CLUSTER_NODES)
    if not clusters:
        return {"summarized": 0, "reason": "no_communities"}

    llm = get_llm()

    # Build the new summary set FIRST (no DB writes) — so a bad week (every summary fails) never wipes
    # the prior week's good summaries (DELETE-then-CREATE is non-atomic). Replace only if we have ≥1.
    new_rows: list[dict] = []
    for c in clusters[:budget]:  # detect_clusters returns largest-first
        insight_ids = [n for n in c.get("nodes", []) if n.startswith("insight:")][:_MAX_MEMBERS_SAMPLED]
        if len(insight_ids) < 3:
            continue
        async with pool.connection() as db:
            crows = parse_rows(
                await db.query(
                    "SELECT content FROM insight WHERE id IN $ids AND status = 'active'",
                    {"ids": parse_record_ids(insight_ids)},
                )
            )
        contents = [str(r.get("content", "")).strip() for r in crows if r.get("content")]
        if len(contents) < 3:
            continue

        prompt = (
            "These knowledge items are densely interlinked in the graph. In 1-2 sentences, name the "
            "shared theme they form:\n\n" + "\n".join(f"- {x[:200]}" for x in contents)
        )
        try:
            # No outer wait_for: CLIProvider owns the subprocess timeout + reaping; wrapping it in a
            # SHORTER outer wait_for would cancel mid-call and ORPHAN the claude subprocess. Non-fatal.
            summary = await llm.complete(prompt, max_tokens=160)
        except Exception as exc:
            logger.warning("community summary failed for %s (non-fatal): %s", c.get("id"), exc)
            continue
        summary = (summary or "").strip()
        if not summary:
            continue

        new_rows.append(
            {
                "label": str(c.get("label", c.get("id"))),
                "summary": summary,
                "mc": len(contents),  # items actually summarized (insights), not total cluster node_count
                "layer": c.get("dominant_layer"),
            }
        )

    if not new_rows:
        return {"summarized": 0, "communities_detected": len(clusters), "reason": "no_summaries_kept_prior"}

    async with pool.connection() as db:
        await db.query("DELETE community_summary WHERE product = <record>$product", {"product": product_id})
        for row in new_rows:
            await db.query(
                """CREATE community_summary SET
                    product = <record>$product, cluster_label = $label, summary = $summary,
                    member_count = $mc, dominant_layer = $layer, created_at = time::now()""",
                {"product": product_id, **row},
            )

    logger.info("community_summarizer: wrote %d community summaries", len(new_rows))
    return {"summarized": len(new_rows), "communities_detected": len(clusters)}
