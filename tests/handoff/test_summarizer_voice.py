"""Boundary tests for completion summarizer voice — A6 AC 5, sentinel check."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.handoff.summarizer import SUMMARY_GENERIC_STRINGS, _fallback_summary, summarize

# ---------------------------------------------------------------------------
# AC 5 — completion summary uses partnership voice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completion_summary_uses_partnership_pronouns():
    result_dict = {"completed": 3, "failed": 0, "blocked": 0, "total_units": 3, "spec_status": "verifying"}
    llm_response = "We finished all three units cleanly — want me to run a spec review before we ship?"

    import core.engine.handoff.summarizer as summ_module

    with patch.object(summ_module.llm, "complete", new_callable=AsyncMock, return_value=llm_response):
        summary = await summarize(result_dict, agent="claude_code")

    lowered = summary.lower()
    assert "we " in lowered or "our " in lowered or " us" in lowered, (
        f"Summary missing partnership pronouns: {summary!r}"
    )


@pytest.mark.asyncio
async def test_completion_summary_contains_observation_or_offer():
    result_dict = {"completed": 2, "failed": 1, "blocked": 0, "total_units": 3}
    llm_response = "We completed 2 units but one auth test is still failing — want me to spec the fix?"

    import core.engine.handoff.summarizer as summ_module

    with patch.object(summ_module.llm, "complete", new_callable=AsyncMock, return_value=llm_response):
        summary = await summarize(result_dict, agent="claude_code")

    # Must contain an offer signal
    offer_tokens = ["want me", "should we", "?"]
    assert any(t in summary.lower() for t in offer_tokens), f"Summary missing observation/offer: {summary!r}"


# ---------------------------------------------------------------------------
# Sentinel check — summary never contains generic completion strings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_never_generic_completion_string():
    result_dict = {"completed": 1, "failed": 0, "blocked": 0, "total_units": 1}
    llm_response = "Task completed successfully"

    import core.engine.handoff.summarizer as summ_module

    with patch.object(summ_module.llm, "complete", new_callable=AsyncMock, return_value=llm_response):
        summary = await summarize(result_dict, agent="claude_code")

    assert summary not in SUMMARY_GENERIC_STRINGS, (
        f"Hand-off summary fell back to generic completion string: {summary!r}"
    )


@pytest.mark.asyncio
async def test_summary_falls_back_gracefully_on_llm_failure():
    result_dict = {"completed": 1, "failed": 0, "blocked": 0, "total_units": 1}

    import core.engine.handoff.summarizer as summ_module

    async def _fail(*args, **kwargs):
        raise ConnectionError("LLM unavailable")

    with patch.object(summ_module.llm, "complete", side_effect=_fail):
        summary = await summarize(result_dict, agent="claude_code")

    assert isinstance(summary, str)
    assert len(summary) > 10
    assert summary not in SUMMARY_GENERIC_STRINGS


@pytest.mark.asyncio
async def test_summary_not_empty():
    result_dict = {"completed": 5, "failed": 0, "blocked": 0, "total_units": 5}
    llm_response = "We shipped all five units — want me to verify the spec before closing it out?"

    import core.engine.handoff.summarizer as summ_module

    with patch.object(summ_module.llm, "complete", new_callable=AsyncMock, return_value=llm_response):
        summary = await summarize(result_dict, agent="claude_code")

    assert len(summary) > 0


# ---------------------------------------------------------------------------
# Fallback summary tests (no LLM dependency)
# ---------------------------------------------------------------------------


def test_fallback_summary_with_failures():
    result = _fallback_summary({"completed": 2, "failed": 1, "blocked": 0, "total_units": 3})
    assert "we " in result.lower() or "our " in result.lower()
    assert result not in SUMMARY_GENERIC_STRINGS
    assert "?" in result  # contains an offer


def test_fallback_summary_with_blocked():
    result = _fallback_summary({"completed": 3, "failed": 0, "blocked": 2, "total_units": 5})
    assert "blocked" in result.lower() or "we" in result.lower()
    assert result not in SUMMARY_GENERIC_STRINGS


def test_fallback_summary_all_complete():
    result = _fallback_summary({"completed": 4, "failed": 0, "blocked": 0, "total_units": 4})
    assert "we" in result.lower()
    assert result not in SUMMARY_GENERIC_STRINGS
