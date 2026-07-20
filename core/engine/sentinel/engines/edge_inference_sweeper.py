"""Sentinel engine: Edge Inference Sweeper.

Runs every 5 minutes. For each active product, infers new causal edges
between journey_event rows (per engine/cognition/edge_inference.py rules).
The journey API may also trigger on-demand inference if the latest sweeper
run is stale.
"""

from __future__ import annotations

import logging

from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


@register_engine(
    "edge_inference_sweeper",
    "*/5 * * * *",
    "Infer causal edges between journey_event rows every 5 minutes",
)
async def run_edge_inference_sweeper(product_id: str = "product:platform") -> dict:
    """Run inference for the product. Returns {edges_written, product_id}."""
    from core.engine.cognition.edge_inference import infer_edges_for_product
    from core.engine.core.db import pool

    new_edges = await infer_edges_for_product(pool, product_id)
    logger.info(
        "edge_inference_sweeper: %d new edges for %s",
        len(new_edges),
        product_id,
    )
    return {"edges_written": len(new_edges), "product_id": product_id}
