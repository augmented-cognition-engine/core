"""capture_outcome — close the action active-loop. Persist every arm execution as an
action_outcome node; on a verified build with a linked spec, advance it to 'built'
(arm-verified in a worktree, awaiting promotion). Fully non-fatal."""

from __future__ import annotations

import logging

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.core.db import pool as default_pool
from core.engine.graph.edge_writer import create_edge

logger = logging.getLogger(__name__)

# Cap on touches edges per outcome — a sweeping refactor can change hundreds of files; we want the
# build's footprint, not a fan-out that drowns the graph. Truncation is logged, never silent.
_MAX_TOUCH = 50


async def capture_outcome(
    solution,
    arm_domain,
    result,
    verdict,
    product_id="product:platform",
    pool=None,
    run_id=None,
    attempts=1,
):
    """Write the outcome; advance the spec to 'built' on pass+spec_id. Never raises.

    Records PARKED distinctly from failed: a parked row means the build was never judged (the
    environment broke), so downstream learning must NOT read it as evidence that this approach
    fails — it is evidence of nothing except a broken environment. `attempts` is the repair-loop
    cost, which is a real signal: an approach that only ever passes on the second try is a
    different animal from one that lands first time.
    """
    pool = pool or default_pool
    try:
        ws = getattr(result, "workspace", None)
        branch = getattr(ws, "branch", None) if ws is not None else None
        wpath = getattr(ws, "path", None) if ws is not None else None
        wroot = getattr(ws, "repo_root", None) if ws is not None else None
        diff = None
        if ws is not None:
            try:
                diff = (ws.diff() or "")[:500]
            except Exception:
                diff = None
        spec_id = getattr(solution, "spec_id", None)
        spec_ref = parse_record_id(spec_id) if spec_id else None
        plan = getattr(result, "plan", None)
        prof = getattr(plan, "profile", None) if plan is not None else None
        pipeline = getattr(plan, "pipeline", None) if plan is not None else None
        pget = (
            (lambda k: getattr(prof, k, None))
            if prof is not None and not isinstance(prof, dict)
            else (lambda k: prof.get(k) if isinstance(prof, dict) else None)
        )
        async with pool.connection() as db:
            created = parse_rows(
                await db.query(
                    "CREATE action_outcome SET product=$p, spec=$spec, arm_domain=$d, intent=$intent, "
                    "passed=$passed, reason=$reason, performed_verbs=$verbs, diff_summary=$diff, "
                    "workspace_branch=$branch, workspace_path=$wpath, workspace_repo_root=$wroot, "
                    "profile_scope=$pscope, profile_novelty=$pnovelty, profile_risk=$prisk, "
                    "profile_verify_depth=$pverify, profile_task_type=$ptask, pipeline=$pipeline, "
                    "parked=$parked, diagnosis=$diagnosis, attempts=$attempts, run=$run",
                    {
                        "p": parse_record_id(product_id),
                        "spec": spec_ref,
                        "d": arm_domain,
                        "intent": (solution.intent or "")[:500],
                        "passed": bool(verdict.passed),
                        "reason": verdict.reason or "",
                        "parked": bool(getattr(verdict, "parked", False)),
                        "diagnosis": getattr(verdict, "diagnosis", "") or "",
                        "attempts": int(attempts),
                        "run": parse_record_id(run_id) if run_id else None,
                        "verbs": [a.verb for a in result.performed],
                        "diff": diff,
                        "branch": branch,
                        "wpath": wpath,
                        "wroot": wroot,
                        "pscope": pget("scope"),
                        "pnovelty": pget("novelty"),
                        "prisk": pget("risk"),
                        "pverify": pget("verify_depth"),
                        "ptask": pget("task_type"),
                        "pipeline": pipeline,
                    },
                )
            )
            outcome_id = str(created[0]["id"]) if created else None
            if verdict.passed and spec_ref is not None:
                await db.query("UPDATE $spec SET status='built'", {"spec": spec_ref})
            if outcome_id:
                await _write_afferent_edges(db, outcome_id, solution, result, verdict, spec_id, pool)
    except Exception as exc:
        logger.warning("capture_outcome failed (non-fatal): %s", exc)


async def _write_afferent_edges(db, outcome_id, solution, result, verdict, spec_id, pool):
    """Edge the outcome back into the graph so the loop is traversable: addresses->spec,
    exercises->capability, touches->graph_file. Idempotent (create_edge dedups), fully non-fatal —
    bookkeeping must never break the build loop. Edges carry passed so traversals weight builds.

    Runs for failed builds too: a failed attempt still addressed a spec and touched files (the
    "this spec has N failed attempts" signal). Only the spec->built advance is gated on passed.

    Edges carry `parked` alongside `passed` so that signal stays honest: a run the environment
    killed is NOT a failed attempt at the spec, and a traversal counting attempts must be able to
    exclude it. Without the flag, every LLM timeout would look like the approach not working.
    """
    meta = {"passed": bool(verdict.passed), "parked": bool(getattr(verdict, "parked", False))}
    try:
        if spec_id:
            await create_edge("outcome_addresses", outcome_id, spec_id, meta, pool=pool)
            # Resolve the spec's capability for an exercises edge (the dynamic reality signal the
            # capability audit reads — stronger than a static glob match).
            cap_rows = parse_rows(await db.query("SELECT capability FROM $spec", {"spec": parse_record_id(spec_id)}))
            cap_id = cap_rows[0].get("capability") if cap_rows else None
            if cap_id:
                await create_edge("outcome_exercises", outcome_id, str(cap_id), meta, pool=pool)
    except Exception as exc:
        logger.warning("afferent spec/capability edges failed (non-fatal): %s", exc)

    try:
        ws = getattr(result, "workspace", None)
        changed = ws.changed_files() if ws is not None and hasattr(ws, "changed_files") else []
        if len(changed) > _MAX_TOUCH:
            logger.info("capture_outcome: %d files changed — recording touches for first %d", len(changed), _MAX_TOUCH)
            changed = changed[:_MAX_TOUCH]
        for path in changed:
            rows = parse_rows(
                await db.query(
                    "SELECT id FROM graph_file WHERE graph_id = 'default' AND path = $path LIMIT 1", {"path": path}
                )
            )
            if rows:
                await create_edge("outcome_touches", outcome_id, str(rows[0]["id"]), meta, pool=pool)
    except Exception as exc:
        logger.warning("afferent touches edges failed (non-fatal): %s", exc)
