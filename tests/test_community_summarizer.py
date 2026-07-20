"""Community summarizer — Louvain clusters over cognify edges → LLM theme summaries (GraphRAG).
Live-verified to detect 13 communities + summarize on the real graph; these lock logic + guards.
See docs/superpowers/specs/2026-06-23-graph-community-summaries-design.md."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401

import pytest


def _clique_edges():
    """6 insight nodes fully interlinked → one Louvain community of ≥5 nodes."""
    nodes = [f"insight:n{i}" for i in range(6)]
    return [{"in": a, "out": b} for i, a in enumerate(nodes) for b in nodes[i + 1 :]]


class _FakeLLM:
    async def complete(self, prompt, max_tokens=160, **kw):
        return "Theme: systematic infra audit methodology."


def _mock_pool(edge_rows, created):
    pool = MagicMock()
    conn = MagicMock()

    async def q(query, params=None):
        if "FROM causes " in query:  # one edge type carries the clique; others empty
            return [edge_rows]
        if query.lstrip().startswith("SELECT in, out"):
            return [[]]
        if "FROM insight" in query:
            return [[{"content": f"knowledge item {i}"} for i in range(6)]]
        if query.lstrip().startswith("DELETE community_summary"):
            return [[]]
        if "CREATE community_summary" in query:
            created.append(params)
            return [[{"id": "community_summary:1"}]]
        return [[]]

    conn.query = q
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.mark.asyncio
def _fires_on(cron: str) -> set[str]:
    """The days a cron ACTUALLY fires, in APScheduler's reading of it.

    Asserting the cron STRING is the weak form and it is how this bug lived: the old
    assertion here was `== "0 5 * * 0"  # Sunday 5 AM`, which passed for months while the
    engine ran on MONDAY. APScheduler reads day-of-week 0=mon..6=sun, not the standard
    crontab 0=sun, and does not translate. Assert the behaviour, not the literal.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apscheduler.triggers.cron import CronTrigger

    tz = ZoneInfo("UTC")
    trigger = CronTrigger.from_crontab(cron, timezone=tz)
    days, prev = set(), datetime(2026, 7, 12, tzinfo=tz)  # a Sunday
    for _ in range(7):
        nxt = trigger.get_next_fire_time(None, prev)
        days.add(nxt.strftime("%A"))
        prev = nxt.replace(hour=23, minute=59)
    return days


async def test_detects_and_summarizes_community(monkeypatch):
    import core.engine.sentinel.engines.community_summarizer as mod

    created: list = []
    monkeypatch.setattr(mod, "pool", _mock_pool(_clique_edges(), created))
    monkeypatch.setattr(mod, "get_llm", lambda: _FakeLLM())

    res = await mod.run_community_summarizer("product:test", budget=5)
    assert res["summarized"] >= 1
    assert res["communities_detected"] >= 1
    assert created and "systematic infra" in created[0]["summary"]
    assert created[0]["mc"] >= 5  # member_count bound param


@pytest.mark.asyncio
async def test_no_edges_is_noop(monkeypatch):
    import core.engine.sentinel.engines.community_summarizer as mod

    monkeypatch.setattr(mod, "pool", _mock_pool([], []))
    res = await mod.run_community_summarizer("product:test")
    assert res == {"summarized": 0, "reason": "no_cognify_edges"}


@pytest.mark.asyncio
async def test_summary_failure_is_non_fatal(monkeypatch):
    import core.engine.sentinel.engines.community_summarizer as mod

    class _BoomLLM:
        async def complete(self, *a, **k):
            raise RuntimeError("cli hung")

    created: list = []
    monkeypatch.setattr(mod, "pool", _mock_pool(_clique_edges(), created))
    monkeypatch.setattr(mod, "get_llm", lambda: _BoomLLM())
    res = await mod.run_community_summarizer("product:test", budget=5)
    assert res["summarized"] == 0  # LLM failed → skipped, never raised
    assert created == []


@pytest.mark.asyncio
async def test_validation():
    import core.engine.sentinel.engines.community_summarizer as mod
    from core.engine.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await mod.run_community_summarizer("no_colon", budget=5)
    with pytest.raises(ValidationError):
        await mod.run_community_summarizer("product:test", budget=0)


def test_registered():
    import core.engine.sentinel.engines.community_summarizer  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "community_summarizer" in engine_registry
    assert _fires_on(engine_registry["community_summarizer"]["cron"]) == {"Saturday"}


@pytest.mark.asyncio
async def test_briefing_renders_community_summaries():
    """The LIVE briefing render (compose_morning_briefing) must CONTAIN the summaries — guards against the
    feature writing a table the rendered briefing never reads (the review-caught inert-feature defect)."""
    from core.engine.voice.briefing import compose_morning_briefing

    payload = {
        "product_id": "product:test",
        "current_phase": "alpha",
        "days_in_phase": 3,
        "top_recommendations": [],
        "open_uncertainty_queries": [],
        "community_summaries": ["Audit-driven infrastructure methodology (34 items)"],
    }
    md = await compose_morning_briefing(payload)
    assert "## Knowledge communities" in md
    assert "Audit-driven infrastructure methodology" in md
