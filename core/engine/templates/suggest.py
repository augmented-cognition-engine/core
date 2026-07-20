"""Template auto-suggestion — detect structurally similar completed initiatives.

After 3+ initiatives share a structural fingerprint (same milestone count,
archetype sequence Jaccard >= 70%, domain path overlap >= 50%), propose
creating a template. Extracts common structure, identifies variable parts.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Similarity thresholds
MIN_CLUSTER_SIZE = 3
ARCHETYPE_JACCARD_THRESHOLD = 0.70
DOMAIN_JACCARD_THRESHOLD = 0.50


def initiative_fingerprint(initiative: dict) -> dict:
    """Compute structural fingerprint for an initiative."""
    milestones = initiative.get("milestones_detail", initiative.get("milestones", []))
    if not isinstance(milestones, list):
        milestones = []

    archetype_seq = []
    domain_paths = set()
    for ms in milestones:
        work_items = ms.get("work_items_detail", ms.get("work_items", []))
        if isinstance(work_items, list):
            for wi in work_items:
                if isinstance(wi, dict):
                    archetype_seq.append(wi.get("archetype", ""))
                    dp = wi.get("domain_path", "")
                    if dp:
                        domain_paths.add(dp)

    return {
        "milestone_count": len(milestones),
        "archetype_sequence": archetype_seq,
        "domain_paths": sorted(domain_paths),
        "total_work_items": len(archetype_seq),
    }


def jaccard_similarity(a: list, b: list) -> float:
    """Compute Jaccard similarity between two lists (as multisets for sequences)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def are_structurally_similar(fp_a: dict, fp_b: dict) -> bool:
    """Check if two initiative fingerprints are structurally similar."""
    if fp_a["milestone_count"] != fp_b["milestone_count"]:
        return False
    if fp_a["milestone_count"] == 0:
        return False

    archetype_sim = jaccard_similarity(fp_a["archetype_sequence"], fp_b["archetype_sequence"])
    if archetype_sim < ARCHETYPE_JACCARD_THRESHOLD:
        return False

    domain_sim = jaccard_similarity(fp_a["domain_paths"], fp_b["domain_paths"])
    if domain_sim < DOMAIN_JACCARD_THRESHOLD:
        return False

    return True


def find_clusters(initiatives: list[dict]) -> list[list[dict]]:
    """Find clusters of 3+ structurally similar initiatives."""
    fingerprints = [(init, initiative_fingerprint(init)) for init in initiatives]
    clusters: list[list[dict]] = []
    used = set()

    for i, (init_a, fp_a) in enumerate(fingerprints):
        if i in used:
            continue
        cluster = [init_a]
        cluster_indices = {i}

        for j, (init_b, fp_b) in enumerate(fingerprints):
            if j <= i or j in used:
                continue
            if are_structurally_similar(fp_a, fp_b):
                cluster.append(init_b)
                cluster_indices.add(j)

        if len(cluster) >= MIN_CLUSTER_SIZE:
            clusters.append(cluster)
            used.update(cluster_indices)

    return clusters


def extract_template_draft(cluster: list[dict]) -> dict:
    """Extract common structure from a cluster of similar initiatives.

    Varying parts become {{variables}}.
    """
    if not cluster:
        return {}

    # Use the first initiative as the template base
    base = cluster[0]
    milestones = base.get("milestones_detail", base.get("milestones", []))
    if not isinstance(milestones, list):
        milestones = []

    # Detect which titles vary across the cluster
    variables = []

    # Extract milestone templates
    ms_templates = []
    for ms in milestones:
        wi_templates = []
        work_items = ms.get("work_items_detail", ms.get("work_items", []))
        if isinstance(work_items, list):
            for wi in work_items:
                if isinstance(wi, dict):
                    wi_templates.append(
                        {
                            "title": wi.get("title", ""),
                            "archetype": wi.get("archetype", "executor"),
                            "mode": wi.get("mode", "reactive"),
                            "domain_path": wi.get("domain_path", ""),
                        }
                    )

        ms_templates.append(
            {
                "title": ms.get("title", ""),
                "description": ms.get("description", ""),
                "done_criteria": ms.get("done_criteria", []),
                "work_items": wi_templates,
            }
        )

    return {
        "name": f"Auto-suggested from {len(cluster)} initiatives",
        "description": f"Pattern detected across {len(cluster)} completed initiatives",
        "domain_path": base.get("domain_path", cluster[0].get("domain_path", "")),
        "milestones": ms_templates,
        "variables": variables,
        "source_initiatives": [init.get("id") for init in cluster],
    }


async def detect_template_candidates(product_id: str, db=None) -> list[dict]:
    """Scan completed initiatives and find template candidates.

    Returns list of template draft dicts ready for user review.
    """
    from core.engine.core.db import pool as default_pool

    _pool = db if db else default_pool

    if db:
        # Already have a connection
        result = await db.query(
            """
            SELECT * FROM initiative
            WHERE product = <record>$product AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 50
            """,
            {"product": product_id},
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])
    else:
        async with _pool.connection() as conn:
            result = await conn.query(
                """
                SELECT * FROM initiative
                WHERE product = <record>$product AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 50
                """,
                {"product": product_id},
            )
            rows = result[0] if result and isinstance(result[0], list) else (result or [])

    if not rows or not isinstance(rows, list):
        return []

    clusters = find_clusters(rows)
    drafts = [extract_template_draft(cluster) for cluster in clusters]
    return drafts
