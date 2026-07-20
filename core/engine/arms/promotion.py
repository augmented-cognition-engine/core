"""Promotion — the gated MUTATING step that ships an arm-built spec.

_merge_and_validate is the safety core: capture the pre-merge SHA, merge --no-ff,
run the gate on the MERGED result, and keep it only if green (else reset --hard back).
A conflict aborts. Base is never left in an unvalidated or conflicted state."""

from __future__ import annotations

import logging
import subprocess

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.core.db import pool as default_pool

logger = logging.getLogger(__name__)


def _git(repo_root, *args):
    return subprocess.run(["git", "-C", repo_root, *args], capture_output=True, text=True)


# Domain-appropriate promotion gate, selected when the caller passes none. A design spec ships a
# .tsx surface, so it must gate on the design-system enforcement battery — the CANONICAL TS suite
# (contrast-AA, token-contract, extension-leakage — the rules the in-loop Python mirror omits),
# run from the canvas package where node_modules exists, on the MERGED result. Everything else
# gates on the Python fast suite. This is what makes "no design slop reaches shipped" actually true.
_DESIGN_GATE = ("bash", "-lc", "cd core/ui/canvas && npx vitest run src/design/__enforcement__")
# A data spec ships a .surql migration — gate it on the REAL apply: test_schema_idempotency applies
# every migration (incl. the merged one) twice against the test DB. It is e2e-marked, so the default
# `make test-fast` (pytest -m "not e2e") SKIPS it — i.e. the default gate is vacuous for migrations.
# Run it explicitly so a broken/non-idempotent migration fails the merge instead of shipping.
_DATA_GATE = ("uv", "run", "pytest", "tests/test_schema_idempotency.py", "-q")
_DEFAULT_GATE = ("make", "test-fast")


def _gate_for_domain(arm_domain) -> tuple:
    """Pick the promotion gate from the building arm's domain (when the caller specifies none)."""
    if arm_domain == "design":
        return _DESIGN_GATE
    if arm_domain == "data":
        return _DATA_GATE
    return _DEFAULT_GATE


def _merge_and_validate(repo_root: str, branch: str, gate_cmd) -> dict:
    """Merge branch into the current base, validate the merged result, keep-or-undo.

    Invariant: on return, base is EITHER at a gate-validated merge OR back at pre_sha.
    Any failure to obtain a gate verdict (missing/empty command, exception) is treated
    exactly like a red gate — the merge is reverted. A failed revert is reported as
    such (never claimed as a successful revert)."""
    if not gate_cmd:
        return {"ok": False, "reason": "no gate command provided"}

    # REFUSE a dirty tree. Not because merging is unsafe — a merge leaves unrelated files alone —
    # but because the REVERT is: on a red gate this function runs `git reset --hard` (discarding
    # every modified tracked file) and `git clean -fd` (deleting every untracked file and directory).
    # Both are aimed at undoing the merge, and neither can tell the merge's mess from YOURS.
    #
    # This repo permanently carries uncommitted work — a parallel session's edits, standing untracked
    # scratch directories. Promoting into that means a red gate silently eats hours of someone else's
    # work. It has never fired only because promotion has never been run for real; "it never happened"
    # is not a safety property, it just means nobody has pulled the pin yet.
    #
    # You cannot know in advance whether you will need the revert. A gate that might have to destroy
    # your work to clean up after itself has no business starting.
    dirty = _git(repo_root, "status", "--porcelain")
    if dirty.returncode != 0:
        return {"ok": False, "reason": "cannot read the working tree state"}
    if dirty.stdout.strip():
        n = len(dirty.stdout.strip().splitlines())
        return {
            "ok": False,
            "reason": (
                f"refusing to promote: the working tree has {n} uncommitted change(s). If the gate "
                "goes red this would `git reset --hard` and `git clean -fd` to undo the merge — "
                "destroying that work, tracked and untracked alike. Commit or stash it, then promote."
            ),
        }

    pre = _git(repo_root, "rev-parse", "HEAD")
    if pre.returncode != 0:
        return {"ok": False, "reason": "cannot resolve base HEAD"}
    pre_sha = pre.stdout.strip()

    # FAIL CLOSED on an empty branch. If the build never committed its work, this branch carries
    # nothing — and `git merge` would answer "Already up to date", exit 0, and let us report a
    # SUCCESSFUL PROMOTION having shipped absolutely nothing. The spec gets marked shipped and the
    # diff evaporates. Dispatch now commits a verified build, but the day that silently stops
    # happening, THIS is the check that must notice — not you, three weeks later, wondering where
    # the feature went.
    ahead = _git(repo_root, "rev-list", "--count", f"{pre_sha}..{branch}")
    if ahead.returncode != 0 or ahead.stdout.strip() in ("", "0"):
        return {
            "ok": False,
            "reason": (
                f"nothing to promote: {branch} has no commits beyond the base. The build's work was "
                "never committed to it, so merging would ship nothing while reporting success."
            ),
            "pre_sha": pre_sha,
        }

    merge = _git(repo_root, "merge", "--no-ff", "-m", f"promote {branch}", branch)
    if merge.returncode != 0:
        _git(repo_root, "merge", "--abort")
        return {"ok": False, "reason": "merge conflict — base moved; re-run the build", "pre_sha": pre_sha}

    def _revert(reason: str, **extra) -> dict:
        reset = _git(repo_root, "reset", "--hard", pre_sha)
        _git(repo_root, "clean", "-fd")  # remove gate-created untracked files
        if reset.returncode != 0:
            post = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
            return {
                "ok": False,
                "pre_sha": pre_sha,
                "post_sha": post,
                "reason": f"{reason} AND revert FAILED — base may hold an unvalidated "
                f"merge; manual intervention required",
            }
        return {"ok": False, "reason": f"{reason}; merge reverted", "pre_sha": pre_sha, **extra}

    try:
        gate = subprocess.run(list(gate_cmd), cwd=repo_root, capture_output=True, text=True)
    except Exception as exc:  # missing binary, permission, etc. — no verdict obtained
        return _revert(f"gate could not run: {exc!r}")
    if gate.returncode != 0:
        return _revert("gate failed", gate_tail=(gate.stdout + gate.stderr)[-500:])

    merge_sha = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    return {"ok": True, "merge_sha": merge_sha, "pre_sha": pre_sha}


async def promote(spec_id, product_id="product:platform", gate_cmd=None, pool=None) -> dict:
    """Human-gated: merge the spec's arm build into base (gate-validated), built→shipped.

    gate_cmd=None (the default) derives a domain-appropriate gate from the building arm
    (design → the TS enforcement battery; else → make test-fast). An explicit gate_cmd wins."""
    pool = pool or default_pool
    try:
        sid = parse_record_id(spec_id)
        async with pool.connection() as db:
            spec = parse_rows(await db.query("SELECT status FROM agent_spec WHERE id = $s", {"s": sid}))
            if not spec or spec[0].get("status") != "built":
                return {"promoted": False, "reason": "spec is not in 'built' state"}
            ao = parse_rows(
                await db.query(
                    # passed = true is LOAD-BEARING, not a tidy-up. A PARKED run (the environment
                    # died mid-build) preserves its worktree on purpose — so its branch still
                    # exists on disk and a bare ORDER BY created_at DESC would happily hand it to
                    # the merge. That would put work NOBODY EVER JUDGED onto master, quietly.
                    # Promote a verified build or promote nothing.
                    "SELECT workspace_branch, workspace_path, workspace_repo_root, arm_domain, created_at FROM action_outcome "
                    "WHERE spec = $s AND passed = true "
                    "AND arm_domain != 'promotion' AND arm_domain != 'rejection' "
                    "ORDER BY created_at DESC LIMIT 1",
                    {"s": sid},
                )
            )
        if not ao or not ao[0].get("workspace_branch") or not ao[0].get("workspace_repo_root"):
            return {"promoted": False, "reason": "no build/worktree to promote"}
        branch = ao[0]["workspace_branch"]
        repo_root = ao[0]["workspace_repo_root"]
        wpath = ao[0].get("workspace_path")
        # Caller's explicit gate wins; otherwise gate on the building arm's discipline.
        if gate_cmd is None:
            gate_cmd = _gate_for_domain(ao[0].get("arm_domain"))

        # The execution layer writes files into the worktree but does not commit them.
        # Commit the build to its branch so the merge carries the arm's work (ship the
        # exact diff the review lane shows). A no-op commit (nothing staged) is fine.
        if wpath:
            _git(wpath, "add", "-A")
            _git(wpath, "commit", "-m", f"arm build: {branch}")  # nonzero if nothing to commit — ignored

        status = _git(repo_root, "status", "--porcelain")
        if status.stdout.strip():
            return {"promoted": False, "reason": "working tree not clean — commit or stash first"}

        mv = _merge_and_validate(repo_root, branch, gate_cmd)
        if not mv["ok"]:
            return {"promoted": False, "reason": mv["reason"]}

        async with pool.connection() as db:
            await db.query("UPDATE $s SET status='shipped'", {"s": sid})
            await db.query(
                "CREATE action_outcome SET product=$p, spec=$s, arm_domain='promotion', intent=$i, "
                "passed=true, reason='merged', performed_verbs=[], diff_summary=$sha",
                {"p": parse_record_id(product_id), "s": sid, "i": f"promote {branch}", "sha": mv["merge_sha"]},
            )

        if wpath:
            try:
                from core.engine.arms.execution.workspace import Workspace

                Workspace(path=wpath, branch=branch, repo_root=repo_root).discard()
            except Exception as exc:
                logger.warning("promote: worktree discard failed (non-fatal): %s", exc)

        return {"promoted": True, "reason": "merged + shipped", "merge_sha": mv["merge_sha"]}
    except Exception as exc:
        logger.warning("promote failed (non-fatal): %s", exc)
        return {"promoted": False, "reason": str(exc)}


async def reject(spec_id, product_id="product:platform", pool=None) -> dict:
    """Human-gated: discard the arm build, re-queue the spec (built→approved). Base untouched."""
    pool = pool or default_pool
    try:
        sid = parse_record_id(spec_id)
        async with pool.connection() as db:
            ao = parse_rows(
                await db.query(
                    # Same passed = true filter as promote(), for the same reason inverted: the human
                    # is rejecting the BUILT work they reviewed. Without it, a parked run landing
                    # afterwards would make reject() discard the PARKED worktree — destroying the
                    # evidence a human was being asked to look at, and leaving the real build behind.
                    "SELECT workspace_branch, workspace_path, workspace_repo_root, created_at FROM action_outcome "
                    "WHERE spec = $s AND passed = true "
                    "AND arm_domain != 'promotion' AND arm_domain != 'rejection' "
                    "ORDER BY created_at DESC LIMIT 1",
                    {"s": sid},
                )
            )
            await db.query("UPDATE $s SET status='approved'", {"s": sid})
            await db.query(
                "CREATE action_outcome SET product=$p, spec=$s, arm_domain='rejection', "
                "intent='rejected', passed=false, reason='human rejected the build', performed_verbs=[]",
                {"p": parse_record_id(product_id), "s": sid},
            )
        if ao and ao[0].get("workspace_path") and ao[0].get("workspace_repo_root"):
            try:
                from core.engine.arms.execution.workspace import Workspace

                Workspace(
                    path=ao[0]["workspace_path"],
                    branch=ao[0].get("workspace_branch") or "",
                    repo_root=ao[0]["workspace_repo_root"],
                ).discard()
            except Exception as exc:
                logger.warning("reject: worktree discard failed (non-fatal): %s", exc)
        return {"rejected": True, "reason": "build discarded; spec re-queued"}
    except Exception as exc:
        logger.warning("reject failed (non-fatal): %s", exc)
        return {"rejected": False, "reason": str(exc)}
