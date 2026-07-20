# engine/graph/metabolism.py
"""The grounding metabolism (spine) — the graph re-evaluates itself when its
canvas ground shifts.

The `grounds` edge made the reasoning graph canvas-addressable; the metabolism is
the first consumer of its reverse lookup (grounds_of). When a grounded canvas
object changes, the beliefs grounded in it can no longer be assumed current:

  enqueue_reeval_for_object(object) — grounds_of(object) → durable pending requests
  drain_reeval()                    — pending → mark each belief freshness-stale, request done

Marking beliefs freshness-stale (rather than an LLM re-derivation) is the spine's
seam: a changed ground drops its beliefs' freshness_score and clears
freshness_last_computed, so they surface as needing re-evaluation. The LLM
re-derivation (11-SUBSTRATE §5 — recompute confidence from evidence, fire the
ripple) replaces the drain body later; the queue and its provenance stay.

Pure graph reads/writes — no LLM, no organ calls, mirroring grounding.py.

Spec: docs/superpowers/specs/2026-07-15-grounding-metabolism-design.md
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from core.engine.core.db import parse_one, parse_record_id, parse_record_ids, parse_rows
from core.engine.graph.grounding import grounded_in, grounds_of

logger = logging.getLogger(__name__)


class _Rederivation(BaseModel):
    """The LLM's shadow verdict on a destabilized belief — proposed, never applied."""

    still_supported: bool
    proposed_confidence: float
    rationale: str


# The stale floor a drained belief's freshness_score is set to. 0.0 is definitively
# stale (the freshness label is "stale" below 0.4), and distinct from None, which
# means "never computed" — so a drained belief reads as "computed, and now stale".
#
# HONESTY NOTE (adversarial review, 2026-07-15): nothing READS freshness_score yet
# (the orchestrator's _assess_freshness derives freshness from created_at age, not
# this stored score), so this particular write is still unobserved. The metabolism's
# durable, consumed artifact is the reeval_request QUEUE — now surfaced to the
# partner via pending_reevaluations() → ace_status ("which beliefs are destabilized,
# and which ground changed?"). This freshness write is the explicit seam the LLM
# re-derivation replaces; it becomes independently meaningful when a freshness_score
# reader (a stale-beliefs surface) or that seam lands.
STALE_SCORE = 0.0


def _resolve_pool(pool):
    if pool is None:
        from core.engine.core.db import pool as default_pool

        return default_pool
    return pool


async def enqueue_reeval_for_object(object_id, *, reason: str = "ground_changed", pool=None) -> int:
    """Enqueue the beliefs grounded in a changed canvas object for re-evaluation.

    Rides grounds_of: ONLY the beliefs grounded in this object are enqueued, never
    beliefs grounded elsewhere (a false enqueue would re-evaluate unrelated beliefs).
    Idempotent — a second change before a drain does not stack a duplicate pending
    request for the same (belief, object). Returns the number of NEW pending requests.
    """
    pool = _resolve_pool(pool)
    beliefs = await grounds_of(object_id, pool=pool)
    if not beliefs:
        return 0

    obj_rec = parse_record_id(object_id)
    created = 0
    async with pool.connection() as db:
        for belief_id in beliefs:
            belief_rec = parse_record_id(belief_id)
            existing = parse_rows(
                await db.query(
                    "SELECT id FROM reeval_request WHERE belief = $b AND trigger_object = $o "
                    "AND status = 'pending' LIMIT 1",
                    {"b": belief_rec, "o": obj_rec},
                )
            )
            if existing:
                continue
            await db.query(
                "CREATE reeval_request SET belief = $b, trigger_object = $o, reason = $reason, "
                "status = 'pending', created_at = time::now()",
                {"b": belief_rec, "o": obj_rec, "reason": reason},
            )
            created += 1
    return created


async def pending_reevaluations(*, limit: int = 20, pool=None) -> list[dict]:
    """The beliefs currently pending re-evaluation — the metabolism made observable
    to the partner ("3 beliefs destabilized; the pricing frame changed"). Read-only.

    Newest first. Each entry carries the belief's readable content, which canvas
    object destabilized it, and why. A request whose belief no longer resolves is
    omitted (the surface shows live beliefs only); this never raises. This is a
    durable-queue reader — it does not depend on the freshness-stale drain body,
    so it stays valid when the LLM re-derivation replaces that seam.
    """
    pool = _resolve_pool(pool)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT belief, trigger_object, reason, created_at, proposed_confidence, "
                "still_supported, rederivation_rationale FROM reeval_request "
                "WHERE status = 'pending' ORDER BY created_at DESC LIMIT $limit",
                {"limit": limit},
            )
        )
    if not rows:
        return []

    out: list[dict] = []
    async with pool.connection() as db:
        for r in rows:
            belief_id = str(r["belief"])
            # content (insight) or title (decision) — the belief spans reasoning kinds.
            belief = parse_one(await db.query("SELECT content, title FROM $b", {"b": parse_record_id(belief_id)}))
            if belief is None:
                continue  # dangling belief — omit from the surface
            out.append(
                {
                    "belief": belief_id,
                    "belief_content": belief.get("content") or belief.get("title") or belief_id,
                    "trigger_object": str(r["trigger_object"]),
                    "reason": r.get("reason", "ground_changed"),
                    "created_at": r.get("created_at"),
                    # shadow re-derivation (present once rederive_pending has run):
                    "proposed_confidence": r.get("proposed_confidence"),
                    "still_supported": r.get("still_supported"),
                    "rederivation_rationale": r.get("rederivation_rationale"),
                }
            )
    return out


async def drain_reeval(*, limit: int = 200, pool=None) -> int:
    """Mark newly-destabilized beliefs freshness-stale — the always-on interim signal.

    Selects pending requests NOT yet freshness-marked, marks each live belief stale
    (freshness_score=0.0, freshness_last_computed cleared), and flags the request
    `freshness_marked` — it does NOT flip the request to 'done'. The freshness-mark is
    a crude interim signal, not a resolution: the belief still needs re-derivation
    (rederive_pending) and, eventually, apply (§5), so the request stays OPEN. Keeping
    it pending is exactly what lets this cron drain and the manual re-derivation coexist
    on one queue without the drain preempting the re-derivation (adversarial review,
    2026-07-15). A request whose belief is GONE is resolved to 'done' instead — the
    re-evaluation is moot — so the queue never wedges on a dead node. `freshness_marked`
    is filtered with `!= true` (matches false AND legacy NONE). Bounded by `limit`.
    Returns the number processed.

    Marks staleness on beliefs that carry freshness fields (insight, decision — v136);
    a belief of another reasoning kind is flagged but the freshness write is a no-op
    there until the LLM re-derivation (which recomputes all kinds from their evidence).
    """
    pool = _resolve_pool(pool)
    async with pool.connection() as db:
        pending = parse_rows(
            await db.query(
                # v3 requires the ORDER BY idiom in the projection.
                "SELECT id, belief, created_at FROM reeval_request "
                "WHERE status = 'pending' AND freshness_marked != true "
                "ORDER BY created_at LIMIT $limit",
                {"limit": limit},
            )
        )
    if not pending:
        return 0

    processed = 0
    async with pool.connection() as db:
        for req in pending:
            belief_rec = parse_record_id(str(req["belief"]))
            rid = parse_record_id(str(req["id"]))
            alive = parse_rows(await db.query("SELECT id FROM $b", {"b": belief_rec}))
            if alive:
                await db.query(
                    "UPDATE $b SET freshness_score = $s, freshness_last_computed = NONE",
                    {"b": belief_rec, "s": STALE_SCORE},
                )
                # stays 'pending' — freshness-marked, still awaiting re-derivation.
                await db.query(
                    "UPDATE $rid SET freshness_marked = true, drained_at = time::now()",
                    {"rid": rid},
                )
            else:
                # belief gone — the re-evaluation is moot; resolve the request.
                await db.query(
                    "UPDATE $rid SET status = 'done', freshness_marked = true, drained_at = time::now()",
                    {"rid": rid},
                )
            processed += 1
    return processed


def _rederivation_prompt(statement: str, confidence, grounds: list[dict]) -> str:
    if grounds:
        grounds_str = "\n".join(f"- {g['id']}: {g.get('payload')}" for g in grounds)
    else:
        grounds_str = "(the grounding objects are no longer resolvable)"
    return (
        "A belief in a reasoning graph is grounded in canvas objects that have just "
        "changed. Re-evaluate the belief against ONLY the evidence shown — assume "
        "nothing that is not present.\n\n"
        f'Belief: "{statement}"\n'
        f"Current confidence: {confidence}\n\n"
        f"The canvas objects it is grounded in now read:\n{grounds_str}\n\n"
        "Is the belief still supported by this evidence? Give proposed_confidence in "
        "[0,1] and a one-sentence rationale."
    )


async def rederive_belief(belief_id, *, pool=None, llm=None) -> dict | None:
    """SHADOW re-derivation: ask the LLM whether a destabilized belief is still
    supported by its (now-changed) canvas grounds, and at what confidence.

    Returns a proposal {still_supported, proposed_confidence, rationale} — or None
    if the belief no longer resolves (in which case the LLM is NOT called). This
    NEVER modifies the belief; applying a proposal is governed later (11-SUBSTRATE
    §5). The LLM call is the only organ in this module; enqueue/drain stay pure graph.
    """
    pool = _resolve_pool(pool)
    belief_rec = parse_record_id(str(belief_id))
    async with pool.connection() as db:
        belief = parse_one(await db.query("SELECT content, title, confidence FROM $b", {"b": belief_rec}))
    if belief is None:
        return None  # dangling — do not spend an LLM call on a belief that is gone

    grounds = await grounded_in(str(belief_id), pool=pool)
    # objectIds only (artifact/scratch planes) — all that exist today. When discourse
    # (markId) / sheet (sheetId) planes land, gather those too or the LLM re-derives on
    # partial evidence (adversarial review, 2026-07-15 — latent, no impact while
    # CANVAS_TABLES == {canvas_artifact}).
    object_ids = [o for g in grounds for o in g.get("objectIds", [])]
    grounds_content: list[dict] = []
    if object_ids:
        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT id, payload FROM $ids", {"ids": parse_record_ids(object_ids)}))
        grounds_content = [{"id": str(r["id"]), "payload": r.get("payload")} for r in rows]

    statement = belief.get("content") or belief.get("title") or str(belief_id)
    prompt = _rederivation_prompt(statement, belief.get("confidence"), grounds_content)

    if llm is None:
        from core.engine.core.llm import get_llm

        llm = get_llm()
    verdict = await llm.complete_structured(prompt, schema=_Rederivation)
    return {
        "still_supported": verdict.still_supported,
        # clamp to [0,1]: complete_structured guarantees a float, not its range.
        "proposed_confidence": max(0.0, min(1.0, float(verdict.proposed_confidence))),
        "rationale": verdict.rationale,
    }


async def rederive_pending(*, limit: int = 5, pool=None, llm=None) -> int:
    """Bounded SHADOW pass: annotate pending requests that have no proposal yet with
    a re-derivation (proposed_confidence, rationale, still_supported). Returns the
    number re-derived.

    Deliberately OFF the cron: LLM-on-a-schedule risks the CLI-hang-under-load
    trap, so this is an explicit, small-bounded callable. Annotation only — it does
    NOT touch the belief's live confidence and does NOT resolve the request. Both
    this and the cron freshness-drain leave the request OPEN ('pending') and track
    their own work via their own fields (proposed_confidence here, freshness_marked
    there), so neither preempts the other — they coexist on one queue. Resolution
    ('done') is the future §5 apply step.
    """
    pool = _resolve_pool(pool)
    if llm is None:
        from core.engine.core.llm import get_llm

        llm = get_llm()

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT id, belief, created_at FROM reeval_request WHERE status = 'pending' "
                "AND proposed_confidence = NONE ORDER BY created_at LIMIT $limit",
                {"limit": limit},
            )
        )
    if not rows:
        return 0

    rederived = 0
    for r in rows:
        proposal = await rederive_belief(str(r["belief"]), pool=pool, llm=llm)
        if proposal is None:
            continue  # dangling belief — leave the request for the drain to spend
        async with pool.connection() as db:
            await db.query(
                "UPDATE $rid SET proposed_confidence = $pc, rederivation_rationale = $ra, "
                "still_supported = $ss, rederived_at = time::now()",
                {
                    "rid": parse_record_id(str(r["id"])),
                    "pc": proposal["proposed_confidence"],
                    "ra": proposal["rationale"],
                    "ss": proposal["still_supported"],
                },
            )
        rederived += 1
    return rederived
