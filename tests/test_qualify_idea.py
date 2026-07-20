# tests/test_qualify_idea.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.ideas.schemas import QualificationResult


@pytest.mark.asyncio
async def test_qualify_clear_idea_runs_incubation_then_reaches_ready():
    """LLM-clear ideas must NOT bypass enrichment — qualify runs incubate inline.

    Regression: prior fast-path transitioned to `ready` directly without
    writing a brief, leaving ideas surfaced as "ready for review" with no
    review material. Now the fast-path invokes incubate_idea so the brief
    lands before status flips.
    """
    from core.engine.ideas.qualify import qualify_idea

    mock_result = QualificationResult(status="ready", questions=[])
    # Mocked incubation result — represents enriched idea returning from incubate.
    incubated = {
        "status": "ready",
        "brief": {"what": "x", "why": "y", "approach": "z", "risks": "w", "success": "s"},
        "phases": [],
        "connections": [],
        "effort_estimate": None,
    }

    with patch("core.engine.ideas.qualify.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_result)
        with patch("core.engine.ideas.qualify.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(return_value=[[]])
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
            # Lazy import inside the fast-path means we patch incubate's symbol
            # location after the import — the from-import binds it onto qualify's
            # local scope. Patch on the source so the lazy import resolves to mock.
            with patch("core.engine.ideas.incubate.incubate_idea", AsyncMock(return_value=incubated)) as mock_inc:
                result = await qualify_idea(
                    idea={"id": "idea:abc", "raw_input": "Add dark mode to the portal", "status": "captured"},
                    product_id="product:default",
                )

    # Status reflects the enriched outcome from incubate, not a direct transition.
    assert result["status"] == "ready"
    assert result["questions"] is None
    # The critical regression assertion: incubate was actually called.
    mock_inc.assert_awaited_once()


@pytest.mark.asyncio
async def test_qualify_clear_idea_defers_when_incubation_fails():
    """If inline incubation fails, idea stays in current status — never silently 'ready'.

    Without this guard, a transient LLM hiccup could leave an idea flagged
    as "ready for review" with an empty brief — the exact bug this whole
    refactor fixes. The cron retries overnight.
    """
    from core.engine.ideas.qualify import qualify_idea

    mock_result = QualificationResult(status="ready", questions=[])

    with patch("core.engine.ideas.qualify.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_result)
        with patch("core.engine.ideas.qualify.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(return_value=[[]])
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch(
                "core.engine.ideas.incubate.incubate_idea",
                AsyncMock(side_effect=RuntimeError("LLM unreachable")),
            ):
                result = await qualify_idea(
                    idea={"id": "idea:abc", "raw_input": "x", "status": "captured"},
                    product_id="product:default",
                )

    assert result["status"] == "captured"  # unchanged — incubation deferred
    assert result.get("incubation_deferred") is True


@pytest.mark.asyncio
async def test_qualify_ambiguous_idea_asks_questions():
    """Ambiguous idea generates 1-2 questions, transitions to qualifying."""
    from core.engine.ideas.qualify import qualify_idea

    mock_result = QualificationResult(
        status="needs_questions",
        questions=["For how many brands?", "Which brands specifically?"],
    )

    with patch("core.engine.ideas.qualify.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_result)
        with patch("core.engine.ideas.qualify.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(return_value=[[]])
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await qualify_idea(
                idea={"id": "idea:abc", "raw_input": "Support multi-brand themes", "status": "captured"},
                product_id="product:default",
            )

    assert result["status"] == "qualifying"
    assert len(result["questions"]) == 2


@pytest.mark.asyncio
async def test_qualify_never_more_than_2_questions():
    """Even if LLM tries to return 3 questions, schema validation caps at 2."""
    from pydantic import ValidationError

    from core.engine.ideas.schemas import QualificationResult

    with pytest.raises(ValidationError):
        QualificationResult(
            status="needs_questions",
            questions=["Q1?", "Q2?", "Q3?"],
        )


@pytest.mark.asyncio
async def test_qualify_answer_transitions_to_ready():
    """Answering all questions transitions idea from open to ready."""
    from core.engine.ideas.qualify import answer_qualifying_questions

    call_count = 0

    async def side_effect(query_str, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Initial SELECT returns qualifying status
            return [
                [
                    {
                        "id": "idea:abc",
                        "status": "open",
                        "qualifying_qs": [{"q": "For how many brands?", "a": None}],
                    }
                ]
            ]
        # UPDATE returns the updated record (now transitions to ready)
        return [
            [
                {
                    "id": "idea:abc",
                    "status": "ready",
                    "qualifying_qs": [{"q": "For how many brands?", "a": "3 — Acme, Bolt, Crest"}],
                }
            ]
        ]

    with patch("core.engine.ideas.qualify.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=side_effect)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await answer_qualifying_questions(
            idea_id="idea:abc",
            answers=["3 — Acme, Bolt, Crest"],
        )

    assert result["status"] == "ready"
