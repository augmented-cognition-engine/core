# engine/graph/cooccurrence.py
"""Post-task co-occurrence tracking for synaptic graph.

After every task completes, extracts which subdomains were touched together
and updates synapse co-occurrence counters. Creates observed synapses on
first co-occurrence. No LLM calls.

Spec: docs/superpowers/specs/2026-03-21-phase2a-synaptic-graph.md §3
"""

from __future__ import annotations

import logging

from core.engine.core.db import pool

logger = logging.getLogger(__name__)

_STRENGTH_DIVISOR = 50


def calculate_strength(co_occurrence: int) -> float:
    """Linear strength: min(1.0, co_occurrence / 50)."""
    return min(1.0, co_occurrence / _STRENGTH_DIVISOR)


def normalize_pair(a: str, b: str) -> tuple[str, str]:
    """Canonicalize edge direction for bidirectional observed synapses."""
    return (min(a, b), max(a, b))


def extract_subdomain_pairs(task: dict) -> list[tuple[str, str]]:
    """Extract unique subdomain pairs from a task record.

    Uses the discipline field (flat string) as the primary identifier.
    Falls back to legacy domain_path (dotted) for old records.
    """
    discipline = task.get("discipline", "")
    domain_path = task.get("domain_path", "")

    # Derive task_subdomain: prefer discipline, fall back to parts[1] of dotted path
    if discipline:
        task_subdomain = discipline
    else:
        parts = domain_path.split(".")
        if len(parts) < 2:
            return []
        task_subdomain = parts[1]

    cross_domain = task.get("intelligence_loaded", {}).get("cross_domain", [])

    subdomains_touched = set()
    for cd in cross_domain:
        slug = cd.get("source_subdomain_slug")
        if slug and slug != task_subdomain:
            subdomains_touched.add(slug)

    pairs = []
    for other in subdomains_touched:
        a, b = normalize_pair(task_subdomain, other)
        if (a, b) not in pairs:
            pairs.append((a, b))

    return pairs


async def track(task_record: dict, product_id: str) -> list[dict]:
    """Track co-occurrence for a completed task. Returns list of updated synapses."""
    pairs = extract_subdomain_pairs(task_record)
    if not pairs:
        return []

    updated = []
    async with pool.connection() as db:
        for slug_a, slug_b in pairs:
            res_a = await db.query(
                "SELECT id FROM subdomain WHERE slug = <string>$slug LIMIT 1",
                {"slug": slug_a},
            )
            res_b = await db.query(
                "SELECT id FROM subdomain WHERE slug = <string>$slug LIMIT 1",
                {"slug": slug_b},
            )

            rows_a = res_a[0] if res_a and isinstance(res_a[0], list) else (res_a or [])
            rows_b = res_b[0] if res_b and isinstance(res_b[0], list) else (res_b or [])

            if not rows_a or not rows_b:
                logger.warning("Could not resolve subdomains: %s, %s", slug_a, slug_b)
                continue

            id_a = rows_a[0]["id"]
            id_b = rows_b[0]["id"]

            in_id, out_id = normalize_pair(str(id_a), str(id_b))

            # The previous UPSERT-with-conditional-SET (IF origin THEN origin
            # ELSE $origin END, etc.) was failing on the CREATE branch: those
            # IF clauses reference fields that don't exist on a not-yet-created
            # row, so they bound to NONE, and CREATE was silently rejected
            # because `direction` and `origin` are SCHEMAFULL-required with
            # no DEFAULT. Net effect: synapse table stayed empty forever even
            # though track() ran on every task completion.
            #
            # For cooccurrence-tracked synapses, direction='bidirectional',
            # origin='observed', confirmed=false are constants — the
            # preservation logic was unneeded. Set them unconditionally so
            # CREATE actually succeeds.
            await db.query(
                """
                UPSERT synapse SET
                    `in` = <record>$in,
                    `out` = <record>$out,
                    product = <record>$product,
                    direction = $direction,
                    origin = $origin,
                    co_occurrence += 1,
                    last_fired = time::now()
                WHERE `in` = <record>$in AND `out` = <record>$out AND product = <record>$product
                """,
                {
                    "product": product_id,
                    "in": in_id,
                    "out": out_id,
                    "origin": "observed",
                    "direction": "bidirectional",
                },
            )
            # Recalculate strength from the updated co_occurrence value.
            # math::min() in SurrealDB v3 takes a single array argument, not
            # two scalars — the prior `math::min(1.0, co_occurrence / 50.0)`
            # was raising "Incorrect arguments" silently, which is why
            # synapse rows always had strength=0.0 even after many co-occurs.
            result = await db.query(
                """
                UPDATE synapse SET
                    strength = math::min([1.0, co_occurrence / 50.0])
                WHERE `in` = <record>$in AND `out` = <record>$out AND product = <record>$product
                """,
                {"product": product_id, "in": in_id, "out": out_id},
            )

            from core.engine.core.db import parse_one

            row = parse_one(result)
            if not row:
                continue
            updated.append(row)

            co = row.get("co_occurrence", 0)
            threshold = row.get("dismiss_threshold", 10)
            confirmed = row.get("confirmed", False)
            if not confirmed and co >= threshold:
                logger.info(
                    "Synapse proposal: %s <-> %s (co_occurrence=%d, threshold=%d)",
                    slug_a,
                    slug_b,
                    co,
                    threshold,
                )

    return updated
