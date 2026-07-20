from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_classify_trivial_commit_skipped():
    """fix/chore/style/test/docs/ci prefixes → immediate None, no LLM."""
    from core.engine.scanner.scanner import _classify_commit_decision

    assert await _classify_commit_decision("fix typo", "", []) is None
    assert await _classify_commit_decision("chore: bump deps", "Updated versions", []) is None
    assert await _classify_commit_decision("style: reformat", "", []) is None
    assert await _classify_commit_decision("test: add unit tests", "Added coverage", []) is None
    assert await _classify_commit_decision("docs: update README", "", []) is None
    assert await _classify_commit_decision("ci: update workflow", "", []) is None


@pytest.mark.asyncio
async def test_classify_feat_returns_none():
    """feat: prefix returns None — implementation step, not a decision.
    The graph_decision record is still created by the scanner; it just
    has no decision_type.  Intentional decisions belong in ace_capture_decision.
    """
    from core.engine.scanner.scanner import _classify_commit_decision

    result = await _classify_commit_decision(
        "feat(orchestration): inject code_context into executor snapshot",
        "",
        ["core/engine/orchestration/executor.py"],
    )
    assert result is None


@pytest.mark.asyncio
async def test_classify_refactor_returns_none():
    """refactor: prefix also returns None — implementation step, not a decision."""
    from core.engine.scanner.scanner import _classify_commit_decision

    result = await _classify_commit_decision(
        "refactor(llm): extract provider abstraction for model-agnostic routing",
        "",
        ["core/engine/core/llm.py"],
    )
    assert result is None


@pytest.mark.asyncio
async def test_classify_arch_prefix_fast_path():
    """arch: prefix is an explicit decision signal — fast-path classifies it."""
    from core.engine.scanner.scanner import _classify_commit_decision

    result = await _classify_commit_decision(
        "arch: adopt pipeline pattern over single-shot LLM for multi-perspective",
        "Evaluated single-shot vs pipeline; pipeline allows per-perspective specialization.",
        ["core/engine/orchestrator/engagement.py"],
    )
    assert result is not None
    assert result["decision_type"] == "architecture"
    assert result["has_decision"] is True


@pytest.mark.asyncio
async def test_classify_no_decision_trivial_prefix():
    """chore: returns None even with body text."""
    from core.engine.scanner.scanner import _classify_commit_decision

    result = await _classify_commit_decision("chore: update dependencies", "Bumped versions", ["requirements.txt"])
    assert result is None


@pytest.mark.asyncio
async def test_classify_llm_fallback_freeform():
    """Freeform message (no conventional prefix) with body → falls through to LLM."""
    from core.engine.scanner.scanner import _classify_commit_decision

    mock_response = {
        "has_decision": True,
        "decision_type": "direction",
        "rationale": "Chose event-driven over polling for lower latency",
        "alternatives": ["polling"],
    }
    with patch("core.engine.core.llm.get_llm") as mock_llm_fn:
        mock_llm = AsyncMock()
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        mock_llm_fn.return_value = mock_llm
        result = await _classify_commit_decision(
            "Switch conductor to event-driven model instead of polling",
            "Polling introduced 5s latency spikes under load. Event-driven eliminates this.",
            ["engine/conductor.py"],
        )
    assert result is not None
    assert result["decision_type"] == "direction"
    assert result["alternatives"] == ["polling"]


@pytest.mark.asyncio
async def test_classify_llm_failure_graceful():
    """LLM failure on freeform commit returns None, doesn't crash."""
    from core.engine.scanner.scanner import _classify_commit_decision

    with patch("core.engine.core.llm.get_llm") as mock_llm_fn:
        mock_llm = AsyncMock()
        mock_llm.complete_json = AsyncMock(side_effect=Exception("LLM unavailable"))
        mock_llm_fn.return_value = mock_llm
        result = await _classify_commit_decision(
            "Switch conductor to event-driven instead of polling",
            "Polling introduced latency spikes under load. Chose events.",
            ["engine/conductor.py"],
        )
    assert result is None


@pytest.mark.asyncio
async def test_classify_llm_timeout_returns_none():
    """LLM call that exceeds 30s timeout returns None gracefully."""
    import asyncio as _asyncio

    from core.engine.scanner.scanner import _classify_commit_decision

    async def _hang(*args, **kwargs):
        await _asyncio.sleep(9999)

    with patch("core.engine.core.llm.get_llm") as mock_llm_fn:
        mock_llm = AsyncMock()
        mock_llm.complete_json = _hang
        mock_llm_fn.return_value = mock_llm
        # Patch wait_for to fire immediately so the test doesn't actually wait 30s
        with patch("asyncio.wait_for", side_effect=_asyncio.TimeoutError):
            result = await _classify_commit_decision(
                "Switch conductor to event-driven instead of polling",
                "Polling introduced latency spikes under load. Chose events.",
                ["engine/conductor.py"],
            )
    assert result is None


@pytest.mark.asyncio
async def test_classify_empty_title_returns_none():
    """Empty title always returns None."""
    from core.engine.scanner.scanner import _classify_commit_decision

    assert await _classify_commit_decision("", "", []) is None
    assert await _classify_commit_decision("", "Some body", ["file.py"]) is None
