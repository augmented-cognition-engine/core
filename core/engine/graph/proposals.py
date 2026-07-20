# engine/graph/proposals.py
"""Synapse proposal logic — list, confirm, dismiss.

Proposals are unconfirmed observed synapses where co_occurrence >= dismiss_threshold.
Confirming enables intelligence loading. Dismissing escalates the threshold.

Spec: docs/superpowers/specs/2026-03-21-phase2a-synaptic-graph.md §4
"""

from __future__ import annotations

from core.engine.core.db import parse_one, parse_record_id, pool


async def list_proposals(product_id: str) -> list[dict]:
    """List all pending synapse proposals for an org."""
    async with pool.connection() as db:
        result = await db.query(
            """
            SELECT
                id, `in`, `out`, co_occurrence, strength, dismiss_threshold, dismissed_at,
                `in`.slug AS from_slug, `out`.slug AS to_slug
            FROM synapse
            WHERE product = <record>$product
              AND confirmed = false
              AND co_occurrence >= dismiss_threshold
            ORDER BY co_occurrence DESC
            """,
            {"product": parse_record_id(product_id)},
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])

    return [
        {
            "id": str(r.get("id", "")),
            "from": str(r.get("in", "")),
            "to": str(r.get("out", "")),
            "from_slug": r.get("from_slug", ""),
            "to_slug": r.get("to_slug", ""),
            "co_occurrence": r.get("co_occurrence", 0),
            "strength": r.get("strength", 0),
            "dismiss_threshold": r.get("dismiss_threshold", 10),
        }
        for r in rows
    ]


async def confirm_proposal(synapse_id: str, user_id: str) -> dict:
    """Confirm a synapse proposal. Enables intelligence loading."""
    async with pool.connection() as db:
        result = await db.query(
            """
            UPDATE <record>$id SET
                confirmed = true,
                confirmed_by = <record>$user
            """,
            {"id": synapse_id, "user": user_id},
        )
        row = parse_one(result)
    return row or {}


async def dismiss_proposal(synapse_id: str) -> dict:
    """Dismiss a synapse proposal. Doubles dismiss_threshold."""
    async with pool.connection() as db:
        current = await db.query("SELECT dismiss_threshold FROM $id", {"id": synapse_id})
        current_row = parse_one(current) or {}
        old_threshold = current_row.get("dismiss_threshold", 10)

        result = await db.query(
            """
            UPDATE <record>$id SET
                dismissed_at = time::now(),
                dismiss_threshold = $new_threshold
            """,
            {"id": synapse_id, "new_threshold": old_threshold * 2},
        )
        row = parse_one(result)
    return row or {}
