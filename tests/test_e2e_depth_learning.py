# tests/test_e2e_depth_learning.py
from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_failing_key_history_deepens_next_classification(db_pool):
    from core.engine.arms.strategy.classify import classify_work
    from core.engine.arms.strategy.depth_scorer import score_depth
    from core.engine.arms.strategy.profile import WorkProfile
    from core.engine.core.db import parse_record_id, pool

    PID = "product:platform"
    MARK = "E2E_LEARN_fix_isolated"

    # Seed >= min_signals failing action_outcome rows for the key (code, fix, isolated).
    async with pool.connection() as db:
        await db.query("DELETE action_outcome WHERE intent = $i", {"i": MARK})
        for _ in range(8):
            await db.query(
                "CREATE action_outcome SET product=$p, arm_domain='code', intent=$i, passed=false, "
                "reason='seed', performed_verbs=[], profile_novelty='fix', profile_risk='isolated'",
                {"p": parse_record_id(PID), "i": MARK},
            )

    async def classifier(s, c, o):
        return WorkProfile(scope="none", novelty="fix", risk="isolated", verify_depth="smoke")

    class _Sol:
        intent = MARK
        product_id = PID

    # With the real scorer reading the seeded failures, the nudge fires -> scope deepened.
    p = await classify_work(_Sol(), classifier=classifier, scorer=score_depth, arm_domain="code")
    assert p.scope == "nearby", p  # learned: this key keeps failing -> deepen one notch

    # A key with no failing history is left as classified.
    async def classifier_clean(s, c, o):
        return WorkProfile(scope="none", novelty="greenfield", risk="systemic", verify_depth="smoke")

    p_clean = await classify_work(_Sol(), classifier=classifier_clean, scorer=score_depth, arm_domain="code")
    assert p_clean.scope == "none", p_clean  # no history -> no nudge

    async with pool.connection() as db:
        await db.query("DELETE action_outcome WHERE intent = $i", {"i": MARK})
