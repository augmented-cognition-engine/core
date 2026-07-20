"""Detective control: any UPDATE/DELETE on the forget_log audit table is recorded.

The append-only PERMISSIONS don't stop a root connection (ACE-core is root). This
EVENT-based detective control records a content-free tamper trail regardless of who
mutates the log — making audit-log tampering visible.
"""

import pytest

from core.engine.core.db import parse_rows


@pytest.fixture(autouse=True)
async def _cleanup(db_pool):
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE forget_log WHERE content_hash = 'tamper_h_88812'")
        await db.query("DELETE forget_log_tamper WHERE content_hash = 'tamper_h_88812'")


@pytest.mark.asyncio
async def test_forget_log_mutation_is_recorded(db_pool):
    async with db_pool.connection() as db:
        await db.query(
            "CREATE forget_log SET insight_id='insight:x88812', content_hash='tamper_h_88812', "
            "reason='r', actor='t', source='test'"
        )
        # tamper: an UPDATE and a DELETE (root bypasses the append-only perms)
        await db.query("UPDATE forget_log SET reason='tampered' WHERE content_hash='tamper_h_88812'")
        await db.query("DELETE forget_log WHERE content_hash='tamper_h_88812'")

        alerts = parse_rows(
            await db.query("SELECT event, content_hash FROM forget_log_tamper WHERE content_hash='tamper_h_88812'")
        )

    events = sorted(a.get("event") for a in alerts)
    assert "UPDATE" in events and "DELETE" in events  # both mutations caught
    # the tamper trail is content-free (only hash + event + target + at)
    assert all("content" not in a for a in alerts)
