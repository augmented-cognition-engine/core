"""Tests for inline playbook suggestion."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def test_jaccard():
    from core.engine.playbooks.inline_suggest import _jaccard

    assert _jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0
    assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0
    assert _jaccard({"a", "b", "c"}, {"b", "c", "d"}) == 0.5
    assert _jaccard(set(), {"a"}) == 0.0


@pytest.fixture
def mock_db(monkeypatch):
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    import core.engine.playbooks.inline_suggest as inline_suggest_module

    monkeypatch.setattr(inline_suggest_module, "pool", mock_pool)
    return mock_conn


@pytest.mark.asyncio
async def test_suggestion_found_when_similar(mock_db):
    call_count = 0

    async def _query(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # milestones
            return [
                {"id": "ms:1", "title": "Design", "domain_path": "tech"},
                {"id": "ms:2", "title": "Build", "domain_path": "tech"},
            ]
        if call_count == 2:  # work items for current
            return [
                {"archetype": "creator", "domain_path": "architecture"},
                {"archetype": "analyst", "domain_path": "architecture"},
            ]
        if call_count == 3:  # past initiatives
            return [{"id": "initiative:past1", "title": "Similar Project"}]
        if call_count == 4:  # work items for past
            return [
                {"archetype": "creator", "domain_path": "architecture"},
                {"archetype": "analyst", "domain_path": "architecture"},
            ]
        return []

    mock_db.query = AsyncMock(side_effect=_query)

    from core.engine.playbooks.inline_suggest import check_for_playbook_suggestion

    result = await check_for_playbook_suggestion("initiative:current", "product:default", threshold=0.5)

    assert result is not None
    assert len(result["similar_initiatives"]) >= 1
    assert result["similar_initiatives"][0]["similarity"] >= 0.5


@pytest.mark.asyncio
async def test_no_suggestion_for_simple_initiative(mock_db):
    mock_db.query.return_value = [{"id": "ms:1", "title": "Only one milestone", "domain_path": "tech"}]

    from core.engine.playbooks.inline_suggest import check_for_playbook_suggestion

    result = await check_for_playbook_suggestion("initiative:simple", "product:default")

    assert result is None


@pytest.mark.asyncio
async def test_no_suggestion_when_no_similar(mock_db):
    call_count = 0

    async def _query(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # milestones
            return [{"id": "ms:1", "title": "A", "domain_path": "a"}, {"id": "ms:2", "title": "B", "domain_path": "b"}]
        if call_count == 2:  # work items for current
            return [{"archetype": "creator", "domain_path": "architecture"}]
        if call_count == 3:  # past initiatives
            return [{"id": "initiative:past1", "title": "Different"}]
        if call_count == 4:  # work items for past — completely different
            return [{"archetype": "reviewer", "domain_path": "security"}]
        return []

    mock_db.query = AsyncMock(side_effect=_query)

    from core.engine.playbooks.inline_suggest import check_for_playbook_suggestion

    result = await check_for_playbook_suggestion("initiative:unique", "product:default", threshold=0.6)

    assert result is None
