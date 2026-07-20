# engine/api/conductor.py
"""REST API for the capability lifecycle conductor."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from core.engine.api._portal_security import verify_product_access
from core.engine.cognition.conductor_phrases import (
    compose_firing_phrase,
    compose_pending_gate_phrase,
    heartbeat_freshness,
)
from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

router = APIRouter(tags=["conductor"])


# Topics that count as "rule firings" worth narrating in the live page.
# Heartbeat is filtered out — it has its own dedicated panel/phrase.
_FIRING_TOPICS: list[str] = [
    "conductor.gate_cleared",
    "conductor.gate_pending",
    "conductor.track_changed",
    "conductor.stall_detected",
    "conductor.action_failed",
    "quality.score_changed",
    "innovation.candidates_ready",
]


def _to_iso(value) -> str | None:
    """Normalize a SurrealDB datetime / string / None to ISO-8601 string.

    SurrealDB hydrates datetime columns as `datetime` objects when reading;
    FastAPI doesn't auto-serialize those when the route returns a plain
    `dict`, so we normalize manually. Mirrors the pattern used by
    engine/cognition/loop_iterations.py and engine/api/journey.py.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


@router.get("/conductor/lifecycle")
async def lifecycle_view(product: str, user=Depends(get_current_user)):
    """All lifecycle tracks grouped by capability with aggregate state."""
    async with pool.connection() as db:
        tracks = parse_rows(
            await db.query(
                """SELECT * FROM capability_lifecycle_track
                   WHERE product = <record>$product
                   ORDER BY capability, dimension""",
                {"product": product},
            )
        )
    return {"tracks": tracks, "count": len(tracks)}


@router.get("/conductor/active-work")
async def active_work(product: str, user=Depends(get_current_user)):
    """Tracks currently in-flight (spec_pending through verifying)."""
    async with pool.connection() as db:
        tracks = parse_rows(
            await db.query(
                """SELECT * FROM capability_lifecycle_track
                   WHERE product = <record>$product
                   AND state IN ['spec_pending', 'spec_review', 'executing', 'verifying']
                   ORDER BY last_transition DESC""",
                {"product": product},
            )
        )
    return {"active": tracks, "count": len(tracks)}


@router.get("/conductor/rules")
async def list_rules(product: str, user=Depends(get_current_user)):
    """All conductor rules with execution stats."""
    async with pool.connection() as db:
        rules = parse_rows(
            await db.query(
                """SELECT * FROM conductor_rule
                   WHERE product = <record>$product OR org IS NONE
                   ORDER BY priority ASC""",
                {"product": product},
            )
        )
    return {"rules": rules, "count": len(rules)}


@router.get("/conductor/templates")
async def list_templates(product: str, scope: str | None = None, user=Depends(get_current_user)):
    """Quality templates with inheritance chain."""
    scope_clause = "AND scope = <string>$scope" if scope else ""
    async with pool.connection() as db:
        templates = parse_rows(
            await db.query(
                f"""SELECT * FROM quality_template
                    {scope_clause}
                    ORDER BY scope, dimension""",
                {"product": product, "scope": scope},
            )
        )
    return {"templates": templates, "count": len(templates)}


@router.get("/conductor/health")
async def conductor_health(product: str, user=Depends(get_current_user)):
    """Conductor operational health."""
    async with pool.connection() as db:
        tracks = parse_rows(
            await db.query(
                "SELECT state, count() as cnt FROM capability_lifecycle_track WHERE product = <record>$product GROUP BY state",
                {"product": product},
            )
        )
        stuck = parse_rows(
            await db.query(
                """SELECT count() as cnt FROM capability_lifecycle_track
                   WHERE product = <record>$product AND stuck_since IS NOT NONE
                   AND stuck_since < time::now() - 24h""",
                {"product": product},
            )
        )
        executions = parse_rows(
            await db.query(
                """SELECT count() as cnt FROM conductor_rule_execution
                   WHERE product = <record>$product AND created_at > time::now() - 24h""",
                {"product": product},
            )
        )

    by_state = {t["state"]: t["cnt"] for t in tracks}
    total = sum(by_state.values())
    stuck_count = stuck[0]["cnt"] if stuck else 0
    fired_24h = executions[0]["cnt"] if executions else 0

    return {
        "tracks_total": total,
        "tracks_by_state": by_state,
        "stuck_count": stuck_count,
        "rules_fired_24h": fired_24h,
    }


@router.get("/conductor/live/{product_id}")
async def get_live_state(
    product_id: str,
    user=Depends(verify_product_access),
) -> dict:
    """Return the live conductor view for a product.

    Cohort B #17. Aggregates four reads against existing tables — no schema
    changes — and renders partner-voice phrases via
    engine/cognition/conductor_phrases.py.

    Response shape:
      {
        "track_states": {<state>: <count>, ...},
        "stuck_count": <int>,
        "heartbeat": {observed_at, is_fresh, age_seconds, phrase},
        "recent_firings": [{id, topic, occurred_at, phrase}, ...],
        "pending_gates":  [{track_id, name, state, stuck_since, phrase}, ...],
        "generated_at": <iso8601>,
        "product_id": <id>,
      }

    SurrealDB v3 traps observed:
      - ORDER BY column must appear in SELECT (occurred_at, stuck_since).
      - `topic IN [...]` works with array literals (probed empirically).
      - datetime columns hydrate as Python datetime → normalize to ISO via
        `_to_iso` for plain-dict JSON responses.
    """
    async with pool.connection() as db:
        # 1. track-state distribution
        state_rows = parse_rows(
            await db.query(
                """SELECT state, count() AS cnt FROM capability_lifecycle_track
                   WHERE product = <record>$pid GROUP BY state""",
                {"pid": product_id},
            )
        )

        # 2. stuck count — mirrors conductor_health helper above.
        stuck_rows = parse_rows(
            await db.query(
                """SELECT count() AS cnt FROM capability_lifecycle_track
                   WHERE product = <record>$pid AND stuck_since IS NOT NONE
                   AND stuck_since < time::now() - 24h""",
                {"pid": product_id},
            )
        )

        # 3. heartbeat — most-recent conductor.heartbeat event.
        # NB: occurred_at MUST appear in SELECT for ORDER BY to work in v3.
        heartbeat_rows = parse_rows(
            await db.query(
                """SELECT id, occurred_at, topic FROM journey_event
                   WHERE product = <record>$pid AND topic = 'conductor.heartbeat'
                   ORDER BY occurred_at DESC LIMIT 1""",
                {"pid": product_id},
            )
        )

        # 4. recent firings — explicit topic IN [...] list (heartbeat excluded).
        firing_rows = parse_rows(
            await db.query(
                """SELECT id, occurred_at, topic, payload FROM journey_event
                   WHERE product = <record>$pid AND topic IN $topics
                   ORDER BY occurred_at DESC LIMIT 20""",
                {"pid": product_id, "topics": _FIRING_TOPICS},
            )
        )

        # 5. pending gates — tracks waiting on human approval. stuck_since in
        # SELECT per the v3 ORDER BY rule. ASC order = oldest first.
        gate_rows = parse_rows(
            await db.query(
                """SELECT id, name, state, stuck_since FROM capability_lifecycle_track
                   WHERE product = <record>$pid AND state = 'gate_pending'
                   ORDER BY stuck_since ASC""",
                {"pid": product_id},
            )
        )

    # ---- transform results ----

    track_states: dict[str, int] = {r["state"]: r["cnt"] for r in state_rows if r.get("state") is not None}
    stuck_count = stuck_rows[0]["cnt"] if stuck_rows else 0

    if heartbeat_rows:
        observed_at_raw = heartbeat_rows[0].get("occurred_at")
        observed_at_iso = _to_iso(observed_at_raw)
    else:
        observed_at_raw = None
        observed_at_iso = None

    hb = heartbeat_freshness(observed_at_raw)
    heartbeat = {
        "observed_at": observed_at_iso,
        "is_fresh": hb["is_fresh"],
        "age_seconds": hb["age_seconds"],
        "phrase": hb["phrase"],
    }

    recent_firings = [
        {
            "id": str(r.get("id", "")),
            "topic": r.get("topic") or "",
            "occurred_at": _to_iso(r.get("occurred_at")) or "",
            "phrase": compose_firing_phrase(r),
        }
        for r in firing_rows
    ]

    pending_gates = [
        {
            "track_id": str(r.get("id", "")),
            "name": r.get("name") or "",
            "state": r.get("state") or "",
            "stuck_since": _to_iso(r.get("stuck_since")),
            "phrase": compose_pending_gate_phrase(r),
        }
        for r in gate_rows
    ]

    return {
        "track_states": track_states,
        "stuck_count": stuck_count,
        "heartbeat": heartbeat,
        "recent_firings": recent_firings,
        "pending_gates": pending_gates,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_id": product_id,
    }


@router.post("/conductor/tracks/{track_id}/approve")
async def approve_gate(track_id: str, user=Depends(get_current_user)):
    """Human approves a pending conductor gate.

    Only emits the event — the conductor's Rule 5 handles the
    state transition to 'executing'. No direct state mutation here.
    """
    from core.engine.events.bus import bus

    product_id = user.get("product", "")
    await bus.emit(
        "conductor.gate_approved",
        {
            "product_id": product_id,
            "track_id": track_id,
            "approved_by": user.get("id", ""),
        },
    )
    return {"approved": True, "track_id": track_id}
