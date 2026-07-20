# engine/product/decisions.py
"""Decision CRUD — PM-level choices with automatic edge creation.

Decisions are distinct from graph_decision (scanner-created from commits).
These are intentional PM choices with rationale and alternatives.
"""

from __future__ import annotations

import logging
import re

from core.engine.core.db import parse_one, parse_rows
from core.engine.graph.edge_writer import create_edge

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")
_REDECISION_SIMILARITY_THRESHOLD = 0.5
_CONFLICT_THRESHOLD_DIRECT = 0.85
_CONFLICT_THRESHOLD_OVERLAP = 0.75


async def check_decision_conflicts(
    content: str,
    product_id: str,
    db_pool,
    similarity_threshold: float = _CONFLICT_THRESHOLD_OVERLAP,
) -> list[dict]:
    """M3: Check semantic similarity of a new decision against existing ones.

    Returns list of conflicting decisions. Empty = no conflicts.
    Each entry: {id, content, similarity_score, conflict_type}

    conflict_type:
      "direct_contradiction" — similarity > 0.85 (same subject, opposite rule)
      "potential_overlap"    — 0.75–0.85 (related, may conflict)
    """
    try:
        from core.engine.core.db import parse_rows as _parse_rows

        async with db_pool.connection() as db:
            rows = _parse_rows(
                await db.query(
                    """SELECT id, title, rationale, created_at FROM decision
                WHERE product = <record>$product AND outcome = 'accepted'
                ORDER BY created_at DESC LIMIT 100""",
                    {"product": product_id},
                )
            )

        conflicts: list[dict] = []
        for row in rows:
            existing_text = f"{row.get('title', '')} {row.get('rationale', '')}".strip()
            sim = _jaccard_similarity(content, existing_text)
            if sim < similarity_threshold:
                continue
            conflict_type = "direct_contradiction" if sim >= _CONFLICT_THRESHOLD_DIRECT else "potential_overlap"
            conflicts.append(
                {
                    "id": str(row.get("id", "")),
                    "content": existing_text[:200],
                    "similarity_score": round(sim, 3),
                    "conflict_type": conflict_type,
                }
            )

        return sorted(conflicts, key=lambda x: x["similarity_score"], reverse=True)
    except Exception as exc:
        logger.warning("check_decision_conflicts failed (non-fatal): %s", exc)
        return []


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall((text or "").lower()))


def _jaccard_similarity(a: str, b: str) -> float:
    """Word-set Jaccard similarity. Cheap, no LLM, no embedder.

    Good enough for "same decision twice" detection at decision titles' typical
    length. For rationale-level matching, upgrade to embedding cosine later.
    """
    sa, sb = _tokenize(a), _tokenize(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


async def find_similar_decisions(
    db,
    product_id: str,
    title: str,
    threshold: float = _REDECISION_SIMILARITY_THRESHOLD,
    limit: int = 5,
) -> list[dict]:
    """Return prior decisions whose title Jaccard-matches above threshold.

    Scans accepted decisions only (superseded ones are already obsolete signals).
    Non-fatal — returns [] on any failure.
    """
    try:
        rows = parse_rows(
            await db.query(
                """SELECT id, title, rationale, created_at FROM decision
                   WHERE product = <record>$product
                     AND outcome = 'accepted'
                   ORDER BY created_at DESC
                   LIMIT 100""",
                {"product": product_id},
            )
        )
        scored = [(row, _jaccard_similarity(title, row.get("title", ""))) for row in rows]
        hits = [row for row, sim in scored if sim >= threshold]
        return hits[:limit]
    except Exception as exc:
        logger.warning("find_similar_decisions failed (non-fatal): %s", exc)
        return []


async def create_decision(
    title: str,
    decision_type: str,
    rationale: str,
    product_id: str,
    alternatives: list[str] | None = None,
    source: str | None = None,
    source_session: str | None = None,
    affected_capabilities: list[str] | None = None,
    affected_capabilities_confidence: float | None = None,
    led_to_ids: list[str] | None = None,
    discipline_hint: str | None = None,
    perspectives: list[dict] | None = None,
    frameworks_used: list[str] | None = None,
    pool=None,
) -> dict:
    """Create a decision record with automatic edge creation.

    `perspectives` and `frameworks_used` are optional lineage metadata used by
    the canvas Decision Ledger to render which agents shaped the decision and
    which frameworks were used. SCHEMALESS table — additive, no migration.

    `affected_capabilities` writes are forward-write coverage for Layer 5
    (decision:lv6stu70piemfwypde2e). When the caller supplies caps:
    - all three columns land atomically in the CREATE
    - `affected_capabilities_inferred_at = time::now()` (forward-write timestamp)
    - `affected_capabilities_confidence` = caller value, or 1.0 default for
      ground-truth (caller-supplied = high confidence)
    When the caller omits caps: the three columns remain NONE, so the nightly
    sentinel / one-time backfill processes the row later. Forward-write closes
    the gap for callers that DO know their caps; sentinel covers the rest.
    """
    if pool is None:
        from core.engine.core.db import pool as default_pool

        pool = default_pool

    # Decide capability writes. Two paths:
    # (a) caller supplied caps  → write atomically with inferred_at=now
    # (b) caller omitted        → leave columns NONE; sentinel handles
    if affected_capabilities is not None:
        caps_value: list[str] | None = list(affected_capabilities)
        caps_conf: float = (
            float(affected_capabilities_confidence)
            if affected_capabilities_confidence is not None
            else 1.0  # caller-supplied caps are ground truth
        )
        caps_sql = (
            ",\n                affected_capabilities = $affected_capabilities"
            ",\n                affected_capabilities_inferred_at = time::now()"
            ",\n                affected_capabilities_confidence = $caps_conf"
        )
    else:
        caps_value = None
        caps_conf = 0.0
        caps_sql = ""

    async with pool.connection() as db:
        similar_prior = await find_similar_decisions(db=db, product_id=product_id, title=title)

        result = await db.query(
            f"""
            CREATE decision SET
                product = <record>$product,
                title = $title,
                decision_type = $decision_type,
                rationale = $rationale,
                alternatives = $alternatives,
                outcome = 'accepted',
                source = $source,
                source_session = IF $source_session THEN <record>$source_session ELSE NONE END,
                discipline_hint = $discipline_hint,
                perspectives = $perspectives,
                frameworks_used = $frameworks_used,
                created_at = time::now(){caps_sql}
            """,
            {
                "product": product_id,
                "title": title,
                "decision_type": decision_type,
                "rationale": rationale,
                "alternatives": alternatives or [],
                "source": source,
                "source_session": source_session,
                "discipline_hint": discipline_hint,
                "perspectives": perspectives or [],
                "frameworks_used": frameworks_used or [],
                "affected_capabilities": caps_value,
                "caps_conf": caps_conf,
            },
        )
        decision = parse_one(result)
        if not decision:
            return {"error": "Failed to create decision"}

    decision_id = str(decision["id"])

    # Create affected edges (decision -> capability)
    for cap_id in affected_capabilities or []:
        await create_edge("affected", decision_id, str(cap_id), pool=pool)

    # Create led_to edges (decision -> spec/initiative/idea)
    for target_id in led_to_ids or []:
        await create_edge("led_to", decision_id, str(target_id), pool=pool)

    if similar_prior:
        decision["similar_prior"] = [
            {"id": str(p.get("id", "")), "title": p.get("title", ""), "created_at": p.get("created_at")}
            for p in similar_prior
        ]
        # Emit event so briefing can flag it
        try:
            from core.engine.events.bus import bus

            await bus.emit(
                "decision.duplicate_suspected",
                {
                    "product_id": product_id,
                    "new_decision_id": decision_id,
                    "similar_ids": [str(p.get("id", "")) for p in similar_prior],
                },
            )
        except Exception as exc:
            logger.debug("duplicate_suspected emit failed (non-fatal): %s", exc)

    # Emit typed Living Canvas event — decision.captured
    try:
        from core.engine.events.canvas import emit_decision_captured

        await emit_decision_captured(
            product_id=product_id,
            decision_id=decision_id,
            title=title,
            affected_capabilities=[str(c) for c in (affected_capabilities or [])],
            source_session=source_session,
        )
    except Exception as exc:
        logger.debug("decision.captured canvas emit failed (non-fatal): %s", exc)

    # Invalidate the AI briefing cache so the next dispatched AI sees this
    # fresh decision immediately, not after the TTL elapses. The briefing
    # surfaces recent decisions, so a stale cache would hide the just-captured
    # one. Cheap and best-effort.
    try:
        from core.engine.ai_briefing import invalidate_briefing_cache

        invalidate_briefing_cache(product_id)
    except Exception as exc:
        logger.debug("AI briefing cache invalidation failed (non-fatal): %s", exc)

    # L9 loop closure: attach a forward prediction so the reconciler can later
    # score accuracy and update archetype_calibration via EMA. Without this,
    # decisions captured via MCP / direct API never enter the L9 → L3 feedback
    # loop, and calibration only updates for canvas/capture-pipeline decisions.
    # Fire-and-forget: attach_prediction is non-blocking via background task so
    # the LLM call (~1-3s) doesn't delay the decision write response.
    try:
        import asyncio

        from core.engine.foresight.forecaster import attach_prediction

        asyncio.create_task(
            attach_prediction(
                decision_id=decision_id,
                decision_content=f"{title}\n\n{rationale}",
                product_id=product_id,
                discipline=discipline_hint or "general",
                pool=pool,
            )
        )
    except Exception as exc:
        logger.debug("attach_prediction task creation failed (non-fatal): %s", exc)

    return decision


async def supersede_decision(
    old_id: str,
    title: str,
    decision_type: str,
    rationale: str,
    product_id: str,
    alternatives: list[str] | None = None,
    discipline_hint: str | None = None,
    pool=None,
) -> dict:
    """Create a new decision that supersedes an old one.

    Raises ValidationError if the old decision is already superseded (prevents
    chains) or if the supersession would create a circular reference.
    """
    if pool is None:
        from core.engine.core.db import pool as default_pool

        pool = default_pool

    from core.engine.core.exceptions import ValidationError

    async with pool.connection() as db:
        # Guard 1: don't supersede a decision that's already been superseded.
        existing = parse_one(await db.query("SELECT outcome FROM ONLY <record>$id LIMIT 1", {"id": old_id}))
        if existing and existing.get("outcome") == "superseded":
            raise ValidationError(f"Decision {old_id} is already superseded — supersede the replacement instead")

        await db.query(
            "UPDATE <record>$old_id SET outcome = 'superseded'",
            {"old_id": old_id},
        )

        result = await db.query(
            """
            CREATE decision SET
                product = <record>$product,
                title = $title,
                decision_type = $decision_type,
                rationale = $rationale,
                alternatives = $alternatives,
                outcome = 'accepted',
                discipline_hint = $discipline_hint,
                created_at = time::now()
            """,
            {
                "product": product_id,
                "title": title,
                "decision_type": decision_type,
                "rationale": rationale,
                "alternatives": alternatives or [],
                "discipline_hint": discipline_hint,
            },
        )
        new_decision = parse_one(result)

    if new_decision:
        await create_edge("supersedes", str(new_decision["id"]), old_id, pool=pool)

    return new_decision or {"error": "Failed to create replacement decision"}


async def list_decisions(
    product_id: str,
    decision_type: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
    pool=None,
) -> list[dict]:
    """List decisions with optional filters."""
    if pool is None:
        from core.engine.core.db import pool as default_pool

        pool = default_pool

    where_parts = ["product = <record>$product"]
    params: dict = {"product": product_id, "limit": limit}

    if decision_type:
        where_parts.append("decision_type = <string>$decision_type")
        params["decision_type"] = decision_type

    if outcome:
        where_parts.append("outcome = <string>$outcome")
        params["outcome"] = outcome

    where_clause = " AND ".join(where_parts)

    async with pool.connection() as db:
        result = await db.query(
            f"SELECT * FROM decision WHERE {where_clause} ORDER BY created_at DESC LIMIT $limit",
            params,
        )
        return parse_rows(result)


async def get_decision(decision_id: str, pool=None) -> dict | None:
    """Get a single decision with its connected edges."""
    if pool is None:
        from core.engine.core.db import pool as default_pool

        pool = default_pool

    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM <record>$id",
            {"id": decision_id},
        )
        decision = parse_one(result)
        if not decision:
            return None

        edges_result = await db.query(
            """SELECT
                (SELECT id, out FROM affected WHERE in = <record>$id) AS affected,
                (SELECT id, out FROM led_to WHERE in = <record>$id) AS led_to,
                (SELECT id, out FROM supersedes WHERE in = <record>$id) AS supersedes
            """,
            {"id": decision_id},
        )
        edge_row = parse_one(edges_result)
        if edge_row:
            decision["edges"] = {
                "affected": edge_row.get("affected", []),
                "led_to": edge_row.get("led_to", []),
                "supersedes": edge_row.get("supersedes", []),
            }

        return decision
