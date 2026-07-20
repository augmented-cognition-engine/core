"""A parked run is evidence of NOTHING. Every reader of action_outcome must know that.

Introducing `parked` created two ways to lie, and both are silent-in-prod bugs:

  1. The depth scorer counts `passed is False` as a failed build. A parked row IS passed=False —
     so a week of LLM timeouts would read as "this profile class keeps failing" and silently
     escalate reasoning depth. The environment breaking is not the work being hard.

  2. Promotion resolves the workspace to merge by taking the LATEST action_outcome for a spec,
     with no filter on passed. A parked run PRESERVES its workspace (that is the whole point) —
     so a park landing after a good build would hand promotion an unjudged branch that still
     exists on disk, and it would merge to master. Before parked existed, a failed build's
     worktree was discarded, so the merge would simply fail. Now it would succeed. Quietly.

Green tests would not have caught either one.
"""

from __future__ import annotations

import pytest


class _FakeDB:
    def __init__(self, rows):
        self.queries: list[tuple[str, dict]] = []
        self._rows = rows

    async def query(self, q, params=None):
        self.queries.append((q.strip(), params or {}))
        return self._rows


class _FakePool:
    def __init__(self, db):
        self._db = db

    def connection(self):
        db = self._db

        class Ctx:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *a):
                return False

        return Ctx()


@pytest.mark.asyncio
async def test_depth_scorer_excludes_parked_runs_from_the_fail_rate():
    """Six environment failures must NOT read as six failed builds."""
    from core.engine.arms.strategy.depth_scorer import score_depth
    from core.engine.arms.strategy.profile import WorkProfile

    # 6 parked (the model was unreachable all afternoon) + 4 genuine passes.
    # If parked counts as failure: 6/10 = 60% fail rate → escalate. That is the lie.
    # Excluding parked: 0/4 = 0% → no escalation.
    rows = [{"passed": False, "parked": True} for _ in range(6)] + [{"passed": True, "parked": False} for _ in range(4)]
    db = _FakeDB(rows)

    profile = WorkProfile(novelty="high", risk="high")
    signal = await score_depth(profile, arm_domain="code", pool=_FakePool(db), min_signals=3)

    assert signal.escalate is False, "an unreachable model is not evidence that the WORK is failing"

    sql, _params = db.queries[0]
    assert "parked" in sql, "the query itself must exclude parked rows, not just the tally"


@pytest.mark.asyncio
async def test_depth_scorer_still_escalates_on_real_failures():
    """The guard must not make the scorer inert — real failures still escalate."""
    from core.engine.arms.strategy.depth_scorer import score_depth
    from core.engine.arms.strategy.profile import WorkProfile

    rows = [{"passed": False, "parked": False} for _ in range(6)] + [
        {"passed": True, "parked": False} for _ in range(2)
    ]
    db = _FakeDB(rows)

    signal = await score_depth(
        WorkProfile(novelty="high", risk="high"), arm_domain="code", pool=_FakePool(db), min_signals=3
    )

    assert signal.escalate is True, "75% of builds genuinely failing SHOULD deepen the reasoning"


@pytest.mark.asyncio
async def test_promotion_never_promotes_an_unjudged_workspace():
    """The dangerous one: a parked run keeps its branch. Promotion must not merge it."""
    from core.engine.arms import promotion

    # The spec is 'built' (an earlier run passed), but the LATEST outcome is a PARKED run whose
    # workspace branch still exists on disk. ORDER BY created_at DESC would hand us that branch.
    db = _FakeDB([{"status": "built"}])
    await promotion.promote("agent_spec:x", pool=_FakePool(db))

    outcome_query = [q for q, _p in db.queries if "FROM action_outcome" in q]
    assert outcome_query, "promotion must look up the build to promote"
    assert "passed = true" in outcome_query[0], (
        "promotion must resolve the branch from a PASSED build only — a parked run was never "
        "judged, and its worktree is preserved, so an unfiltered ORDER BY would merge it to master"
    )
