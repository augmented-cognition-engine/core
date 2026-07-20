# engine/intelligence/compressor.py
"""Insight compressor — greedy embedding-based near-duplicate clustering.

Groups insights with cosine similarity >= CLUSTER_THRESHOLD into clusters,
keeps the highest-confidence insight as the cluster head, and annotates it
with "(+N similar)" where N = cluster_size - 1.

Insights without embeddings are passed through unchanged and appended after
the clustered results.

All failures are non-fatal: any exception returns the original list.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CLUSTER_THRESHOLD = 0.85


def _greedy_cluster(
    insights: list[dict[str, Any]],
    cosine_fn,
) -> list[dict[str, Any]]:
    """Single-pass greedy clustering by embedding similarity.

    For each insight (in order), compare against existing cluster heads.
    If similarity >= CLUSTER_THRESHOLD, join that cluster (keep the head
    with the highest confidence).  Otherwise, start a new cluster.

    Annotates each surviving head with "(+N similar)" where N >= 1.
    """
    # Each cluster: [head, member, member, ...]
    clusters: list[list[dict]] = []

    for insight in insights:
        vec = insight.get("_vec")
        if vec is None:
            # Should not happen here (split before calling), but guard anyway
            clusters.append([insight])
            continue

        placed = False
        for cluster in clusters:
            head = cluster[0]
            head_vec = head.get("_vec")
            if head_vec is None:
                continue
            sim = cosine_fn(vec, head_vec)
            if sim >= CLUSTER_THRESHOLD:
                # Join this cluster; promote if higher confidence
                if insight.get("confidence", 0.0) > head.get("confidence", 0.0):
                    # Swap: current insight becomes head
                    cluster.insert(0, cluster.pop(0))  # keep head slot
                    cluster[0] = insight
                    cluster.append(head)
                else:
                    cluster.append(insight)
                placed = True
                break

        if not placed:
            clusters.append([insight])

    # Build output: head of each cluster, annotated with (+N similar) if needed
    result: list[dict] = []
    for cluster in clusters:
        head = dict(cluster[0])  # copy to avoid mutating original
        n_similar = len(cluster) - 1
        if n_similar > 0:
            head["content"] = f"{head.get('content', '')} (+{n_similar} similar)"
        result.append(head)

    return result


def compress_insights(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compress a list of insights by clustering near-duplicates.

    Splits into with_vec and without_vec subsets, runs greedy clustering on
    with_vec, then appends without_vec unchanged.

    Returns the original list on any failure.
    """
    if not insights:
        return insights

    try:
        from core.engine.search.semantic import cosine_similarity

        with_vec = [i for i in insights if i.get("_vec") is not None]
        without_vec = [i for i in insights if i.get("_vec") is None]

        if not with_vec:
            return insights

        clustered = _greedy_cluster(with_vec, cosine_similarity)
        return clustered + without_vec

    except Exception as exc:
        logger.warning("compressor failed (non-fatal), returning original: %s", exc)
        return insights
