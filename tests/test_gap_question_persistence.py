"""Item I — gap_analyzer's product_question CREATE must set the required `question` field.

`question` is TYPE string (required) on product_question; a CREATE omitting it silently no-ops on
SurrealDB v3 SCHEMAFULL (empty result, no exception) — so gap_analyzer reported questions_generated
while persisting zero rows. Guard that the CREATE always sets question. See
docs/superpowers/specs/2026-06-22-gap-question-persistence-fix.md.
"""

from __future__ import annotations

import pytest


class _RecordingDB:
    def __init__(self):
        self.calls: list = []  # (sql, params)

    async def query(self, sql, params=None):
        self.calls.append((sql, params))
        return [{"id": "product_question:x"}]


@pytest.mark.asyncio
async def test_create_gap_question_sets_required_question():
    from core.engine.sentinel.engines.gap_analyzer import _create_gap_question

    db = _RecordingDB()
    await _create_gap_question(db, slug="mcp_server", gap="No health check endpoint", cap_id="capability:c1")

    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "CREATE product_question" in sql
    assert "question = $q" in sql, "the required `question` field must be in the SET (else CREATE silently no-ops)"
    assert params.get("q"), "the question text param must be bound"


@pytest.mark.asyncio
async def test_create_gap_question_text_is_slug_and_gap():
    from core.engine.sentinel.engines.gap_analyzer import _create_gap_question

    db = _RecordingDB()
    await _create_gap_question(db, slug="auth", gap="No rate limiting on login", cap_id="capability:c2")

    _, params = db.calls[0]
    assert params["q"] == "auth: No rate limiting on login"
