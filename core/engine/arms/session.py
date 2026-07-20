"""run_build_session — many builds, one walk away.

Everything under this makes a SINGLE build durable, honest and self-repairing. This is the loop
that makes it worth leaving alone: take the next approved spec, build it in a fresh dispatch,
record what happened, decide whether to keep going.

Every interesting decision here is about WHEN TO STOP, because a loop that cannot stop for the
right reasons is not autonomy — it is a token furnace with a progress bar:

  PARKED   → stop immediately. The environment is broken (dead model, dead DB). Every subsequent
             build would park against the same corpse, so continuing produces a pile of identical
             non-results and a large bill. Stop, and hand over a diagnosis.
  FAILED   → keep going. That spec was wrong; the next may be fine. But N failures IN A ROW is not
             bad luck, it is a systemically broken engine grinding the backlog into garbage — so a
             consecutive-failure ceiling stops that too.
  NO WORK  → stop, cleanly. Nothing to do is a success, not an error.
  BUDGET   → stop. max_builds is a hard ceiling, always.

Each iteration is a fresh dispatch, so context never accumulates across builds — the property that
makes a long session behave like N short ones instead of one long degrading one.

Never raises. It runs unattended; it does not get to crash.
"""

from __future__ import annotations

import logging
from typing import Any

from core.engine.arms.builder import build_spec
from core.engine.arms.preflight import preflight
from core.engine.arms.run_ledger import reconcile_stale_runs, reconcile_stranded_specs
from core.engine.arms.spec_reality import check_spec_reality
from core.engine.core.config import settings
from core.engine.core.db import parse_record_id, parse_rows
from core.engine.core.db import pool as default_pool
from core.engine.product.prioritizer import ProductPrioritizer

logger = logging.getLogger(__name__)


async def _gap_scores_by_capability(product_id: str, pool=None) -> dict[str, float]:
    """capability slug → urgency of its WORST gap, via ACE's existing prioritizer.

    Deliberately NOT a new ranking. ProductPrioritizer already scores capability gaps against
    phase-relative floors; growing a second, rival scorer here would give the engine two opinions
    about what matters and no way to reconcile them.

    A capability is as urgent as its worst dimension: a capability that is excellent at five things
    and catastrophic at one is not "mostly fine".

    Returns {} on any failure — the caller falls back to FIFO. Ranking is an optimization, and an
    optimization that can halt the build loop is a liability.
    """
    pool = pool or default_pool
    try:
        ranked = await ProductPrioritizer(pool).prioritize(product_id)
    except Exception as exc:
        logger.warning("gap ranking unavailable — falling back to FIFO (non-fatal): %s", exc)
        return {}

    worst: dict[str, float] = {}
    for row in ranked or []:
        slug = row.get("capability_slug")
        if not slug:
            continue
        score = float(row.get("priority_score", 0.0))
        if score > worst.get(slug, float("-inf")):
            worst[slug] = score
    return worst


async def _next_buildable_spec(product_id: str, pool=None, exclude: set[str] | None = None) -> str | None:
    """The most VALUABLE approved spec not yet attempted — the next thing to build. None when dry.

    `exclude` is load-bearing, not a nicety. A FAILED build requeues its spec to 'approved' (correct:
    a failure is retryable). Without the skip-list, the very next read hands back the SAME spec —
    still approved, still top-ranked — so the session re-runs a build it already knows fails, over
    and over, until the consecutive-failure ceiling kills it. One unroutable spec would stall the
    entire backlog while never touching the work it could actually have done. Its repair budget was
    already spent inside dispatch; there is nothing left to gain from a second identical attempt.

    Across SESSIONS the spec is still 'approved' and gets a fresh try — which is right, because the
    world may have changed (a new arm, a fixed dependency) between runs.

    Value = the urgency of the worst gap on the capability this spec addresses. Oldest-first breaks
    ties and is the fallback when nothing is ranked, so a spec with no capability (or a product with
    no gap data at all) is still built rather than stranded forever.

    Re-read and re-ranked on EVERY iteration, on purpose: a build that closes a gap changes what is
    most valuable next. Ranking once per session would have the loop chase a priority order its own
    work had already invalidated.

    'blocked' is deliberately NOT buildable: that is where a parked build puts a spec, and picking
    it back up would re-park it against the same broken environment on a loop.

    RAISES on a DB failure — deliberately, and this is the whole point. None means "the backlog is
    empty", which the loop reports as a clean sweep. Swallowing the error here would turn a dead
    database into the message "no work left: everything is done" — a broken instrument telling you
    it finished. A queue we cannot READ is an error a human must see. The session's own handler
    catches it and stops with needs_human. (The RANKING, by contrast, is allowed to fail quietly:
    it degrades to FIFO, which still builds the right things in a defensible order.)
    """
    pool = pool or default_pool
    async with pool.connection() as db:
        specs = parse_rows(
            await db.query(
                "SELECT id, capability, created_at FROM agent_spec "
                "WHERE product = $p AND status = 'approved' "
                "ORDER BY created_at ASC",
                {"p": parse_record_id(product_id)},
            )
        )
    # Filter in Python rather than in the WHERE clause: the exclusion set is session state, not
    # database state, and threading a growing NOT IN list through SurrealQL buys nothing.
    if exclude:
        specs = [s for s in specs if str(s["id"]) not in exclude]
    if not specs:
        return None

    # Belt AND braces. _gap_scores_by_capability guards itself, but the guard that matters is the
    # one at the decision point: NOTHING about ranking may stop the loop from building. The queue
    # read above raises (a queue we cannot read is a fact a human must see); the ranking below
    # degrades to FIFO (a loop that builds the oldest thing is still a working loop).
    try:
        scores = await _gap_scores_by_capability(product_id, pool=pool)
        slug_by_id = await _capability_slugs(product_id, pool=pool) if scores else {}
    except Exception as exc:
        logger.warning("spec ranking failed — building oldest-first instead (non-fatal): %s", exc)
        scores, slug_by_id = {}, {}

    if not scores:
        return str(specs[0]["id"])  # FIFO — the specs are already oldest-first

    def _value(idx_spec: tuple[int, dict]) -> tuple[float, int]:
        idx, spec = idx_spec
        cap_id = spec.get("capability")
        slug = slug_by_id.get(str(cap_id)) if cap_id else None
        # -idx so that among equal scores the EARLIER (older) spec sorts first: FIFO tiebreak.
        return (scores.get(slug or "", 0.0), -idx)

    best = max(enumerate(specs), key=_value)[1]
    return str(best["id"])


async def _spec_objective(spec_id: str, pool=None) -> str:
    """The spec's objective text — what the reality check reads. "" on any failure (then the check
    finds nothing and we build, which is the safe error)."""
    pool = pool or default_pool
    try:
        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT objective FROM $s", {"s": parse_record_id(spec_id)}))
        return (rows[0].get("objective") or "") if rows else ""
    except Exception as exc:
        logger.warning("could not read spec objective (non-fatal): %s", exc)
        return ""


async def _count_unapproved_specs(product_id: str, pool=None) -> int:
    """How many specs are waiting on a HUMAN's approval, not on us.

    Without this, an empty build queue reports "no work left" — which reads as a clean sweep, go
    home. In production that was a lie: 16 specs sat in draft awaiting approval, `ace_pending_gates`
    reported 0, and the loop would have done nothing, successfully, forever.

    "Nothing to do" and "nothing you've let me do" are different facts demanding opposite responses.

    Fail-safe: 0 on any error. A broken count must never turn a working session into an error.
    """
    pool = pool or default_pool
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT count() FROM agent_spec WHERE product = $p AND status = 'draft' GROUP ALL",
                    {"p": parse_record_id(product_id)},
                )
            )
        return int(rows[0].get("count", 0)) if rows else 0
    except Exception as exc:
        logger.debug("could not count unapproved specs (non-fatal): %s", exc)
        return 0


async def _capability_slugs(product_id: str, pool=None) -> dict[str, str]:
    """capability record id → slug. The prioritizer speaks in slugs; agent_spec.capability is a
    record id, so something has to bridge them. Returns {} on failure (→ FIFO)."""
    pool = pool or default_pool
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT id, slug FROM capability WHERE product = $p",
                    {"p": parse_record_id(product_id)},
                )
            )
        return {str(r["id"]): r.get("slug", "") for r in rows}
    except Exception as exc:
        logger.warning("capability slug lookup failed — ranking degrades to FIFO: %s", exc)
        return {}


async def run_build_session(
    product_id: str = "product:platform",
    max_builds: int = 5,
    pool=None,
) -> dict[str, Any]:
    """Build approved specs, one at a time, until work / budget / health runs out.

    Returns a summary a human (or a harness) can act on without reading a single log line:
    what got built, what failed, why it stopped, and whether it needs a human.
    """
    built: list[dict] = []
    failed: list[dict] = []
    consecutive_failures = 0
    ceiling = max(1, int(getattr(settings, "build_session_failure_ceiling", 3)))
    reconciled = 0
    released = 0
    warning = ""
    already_built: list[dict] = []
    # Specs attempted in THIS session. A failed build requeues its spec to 'approved', so without
    # this the next read hands the same spec straight back and the loop grinds on it forever.
    attempted: set[str] = set()

    try:
        # Check the engine BEFORE the drive. The session stops well once it is running, but it would
        # otherwise happily begin a long unattended run on a provider that cannot survive one — and
        # you would find that out at 3am, from a wedged process and an empty branch list. A check
        # that costs seconds and fails with a diagnosis beats eight hours that fail with silence.
        # sustained=True UNCONDITIONALLY: one CodeArm build is four-plus model calls before it writes
        # a line, and a real max_builds=1 run wedged for 24 minutes at 0% CPU. Every build session is
        # sustained load; there is no 'short' one.
        check = await preflight(sustained=True)
        if check.warning:
            # Not a reason to stop you — but you should not mistake a 20-minute build for a hang.
            logger.warning("preflight: %s", check.warning)
            warning = check.warning
        if not check.ok:
            return _summary(
                built,
                failed,
                reconciled,
                released,
                "preflight failed",
                diagnosis=check.diagnosis,
                needs_human=True,
            )

        # Close out zombies BEFORE starting: runs a dead process left at 'running' forever. Left
        # alone they turn the parked signal into noise.
        reconciled = await reconcile_stale_runs(product_id=product_id, pool=pool) or 0
        # THEN release specs stranded in 'building' by a dead process. Order matters: the call above
        # has just parked every run nobody is coming back to, so a spec that still has a 'running'
        # run is genuinely in flight and must not be released out from under it.
        released = await reconcile_stranded_specs(product_id=product_id, pool=pool) or 0

        while len(built) + len(failed) < max_builds:
            spec_id = await _next_buildable_spec(product_id, pool=pool, exclude=attempted)
            if spec_id is None:
                waiting = await _count_unapproved_specs(product_id, pool=pool)
                # An empty queue is only a clean sweep if the backlog is ACTUALLY empty. If specs are
                # sitting in draft, the queue is empty because nobody approved anything — a fact that
                # needs a person, not a cheerful "no work left". But only ALARM if we built nothing:
                # having drained the approved queue is a good day's work, and drafts remaining is
                # then information, not an emergency.
                if waiting and not built and not failed:
                    return _summary(
                        built,
                        failed,
                        reconciled,
                        released,
                        "nothing approved",
                        diagnosis=(
                            f"The build queue is empty, but {waiting} spec(s) are sitting in draft "
                            "awaiting YOUR approval — nothing has been authorised to build. This is not "
                            "'all done'. Review them (ace_roadmap) and approve with ace_approve_gate."
                        ),
                        needs_human=True,
                        awaiting_approval=waiting,
                        already_built=already_built,
                    )
                return _summary(
                    built,
                    failed,
                    reconciled,
                    released,
                    "no work left",
                    awaiting_approval=waiting,
                    warning=warning,
                    already_built=already_built,
                )

            attempted.add(spec_id)

            # Do NOT rebuild what already exists. Five of the sixteen drafts audited were already
            # fully implemented — approve those and walk away, and ACE spends the night rebuilding a
            # synthesizer it already has, quite possibly overwriting working code with a worse copy
            # of itself. The check fails OPEN (unsure => build), because a false "not built" costs
            # 20 minutes while a false "already built" means real work silently never happens.
            objective = await _spec_objective(spec_id, pool=pool)
            if objective:
                reality = await check_spec_reality(objective, product_id=product_id)
                if reality.already_exists:
                    logger.warning("spec %s appears ALREADY BUILT — skipping: %s", spec_id, reality.evidence)
                    already_built.append(
                        {"spec": spec_id, "confidence": reality.confidence, "evidence": reality.evidence}
                    )
                    continue

            outcome = await build_spec(spec_id, product_id=product_id, pool=pool)

            if outcome.get("parked"):
                # The environment is dead. It will be just as dead for the next spec.
                return _summary(
                    built,
                    failed,
                    reconciled,
                    released,
                    "parked",
                    diagnosis=outcome.get("diagnosis") or outcome.get("reason", ""),
                    needs_human=True,
                )

            if outcome.get("built"):
                consecutive_failures = 0  # the engine works — the streak is broken
                built.append({"spec": spec_id, "branch": outcome.get("branch")})
                continue

            consecutive_failures += 1
            failed.append({"spec": spec_id, "reason": outcome.get("reason", "")})
            if consecutive_failures >= ceiling:
                return _summary(
                    built,
                    failed,
                    reconciled,
                    released,
                    "too many consecutive failures",
                    diagnosis=(
                        f"{consecutive_failures} builds failed in a row. That is not one bad spec — "
                        "something systemic is wrong (the model, a dependency, the repo). Stopping "
                        "rather than grinding the rest of the backlog into failed builds."
                    ),
                    needs_human=True,
                )

        return _summary(
            built, failed, reconciled, released, "budget exhausted", warning=warning, already_built=already_built
        )

    except Exception as exc:
        logger.warning("build session aborted (non-fatal): %s", exc)
        return _summary(
            built,
            failed,
            reconciled,
            released,
            "error",
            diagnosis=f"{type(exc).__name__}: {exc}",
            needs_human=True,
        )


def _summary(
    built: list[dict],
    failed: list[dict],
    reconciled: int,
    released: int,
    stopped_because: str,
    diagnosis: str = "",
    needs_human: bool = False,
    awaiting_approval: int = 0,
    warning: str = "",
    already_built: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "built": built,
        "failed": failed,
        "reconciled_zombies": reconciled,
        "released_specs": released,
        # Specs in draft that a HUMAN must approve. Reported ALWAYS, because an empty queue is
        # ambiguous until you know this number: "everything is done" and "nothing is authorised"
        # look identical from inside the loop, and only one of them is good news.
        "awaiting_approval": awaiting_approval,
        "stopped_because": stopped_because,
        "diagnosis": diagnosis,
        "needs_human": needs_human,
        # Something true you should know that is NOT a reason to stop you (e.g. "this provider is
        # slow — a build takes 20 minutes"). A gate may only REFUSE for what it has established;
        # everything else it merely tells you.
        "warning": warning,
        # Specs the loop refused to rebuild because the work is already in the codebase. Reported,
        # never silently deleted: the loop does not get to close your specs. You do.
        "already_built": already_built or [],
    }
