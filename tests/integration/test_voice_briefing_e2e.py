"""End-to-end: run_briefing_generator on product:platform produces a partner-voice briefing."""

from __future__ import annotations

import re

import pytest


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_run_briefing_generator_produces_partner_voice_briefing(db_pool):
    from core.engine.product.feature_flags import set_phase_aware_ranking_enabled
    from core.engine.sentinel.engines.briefing import run_briefing_generator

    pid = "product:platform"
    await set_phase_aware_ranking_enabled(db_pool, pid, True)
    try:
        result = await run_briefing_generator(pid)
        assert result["briefings_generated"] == 1
        assert result["format"] == "partner_voice_v1"

        from core.engine.core.db import parse_rows

        async with db_pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT content, format, payload_ref, period, metrics FROM briefing "
                    "WHERE product = <record>$pid ORDER BY created_at DESC LIMIT 1",
                    {"pid": pid},
                )
            )
        assert rows
        b = rows[0]
        assert b["format"] == "partner_voice_v1"
        assert b["payload_ref"] is not None
        assert b["period"]
        assert b["metrics"] is not None

        content = b["content"]
        # Structure D acceptance: lede paragraph + Focus this week + (conditional Open questions) + footer
        assert "## Focus this week" in content
        assert "<details>" in content
        # Has at least one we/our/us in the content
        assert re.search(r"\b(we|our|us)\b", content, re.IGNORECASE)
    finally:
        await set_phase_aware_ranking_enabled(db_pool, pid, False)
