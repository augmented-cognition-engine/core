"""Stage 2 of the A0 ambient trigger: surface the (trustworthy) System A journey as cited context.

Given a fired gate decision, query the code-intelligence journey engine and return grounded, cited
context OR an honest no-answer. Fail-closed throughout: any engine error, a response without
provenance, or an empty projection yields a no-answer — never an uncited or fabricated injection, and
never a raise into the caller's turn. Surfacing targets System A (the deterministic, tested,
honest-about-gaps journey/lens) — the one graph the assessment found trustworthy.
"""

from __future__ import annotations

import pytest

from ace_mcp_client.ambient import GateDecision, surface_code_intelligence

pytestmark = pytest.mark.unit

_TARGET = "core/engine/scanner.py"


def _fired(query: str = "why is scanner.py built this way?") -> GateDecision:
    return GateDecision(fire=True, reason="test", query=query)


def _lens_response(*, snapshot="idx_abc", generation=1, nodes=("graph_file::scanner",), omissions=("no LSP edges",)):
    return {
        "index_snapshot_id": snapshot,
        "index_generation": generation,
        "limitations": ["tree-sitter structure only"],
        "lens": {
            "target_path": _TARGET,
            "nodes": [{"node_id": n} for n in nodes],
            "edges": [],
            "evidence": [{"anchor_id": "a1"}],
            "omissions": list(omissions),
            "degraded_reasons": [],
        },
    }


@pytest.mark.asyncio
async def test_fails_closed_when_engine_errors():
    async def journey(query, target):
        raise RuntimeError("engine down")

    result = await surface_code_intelligence(_fired(), _TARGET, journey=journey)

    assert result.answered is False
    assert result.missing_coverage  # names why it couldn't answer
    assert result.context == ""  # nothing injected on failure


@pytest.mark.asyncio
async def test_no_answer_without_provenance():
    async def journey(query, target):
        response = _lens_response()
        del response["index_snapshot_id"]  # a projection with no provenance
        return response

    result = await surface_code_intelligence(_fired(), _TARGET, journey=journey)

    assert result.answered is False  # never inject uncited material


@pytest.mark.asyncio
async def test_honest_no_answer_on_empty_projection():
    async def journey(query, target):
        return _lens_response(nodes=())

    result = await surface_code_intelligence(_fired(), _TARGET, journey=journey)

    assert result.answered is False
    assert "no LSP edges" in result.missing_coverage  # names the missing coverage honestly


@pytest.mark.asyncio
async def test_injects_cited_context_with_disclosed_gaps():
    async def journey(query, target):
        return _lens_response()

    result = await surface_code_intelligence(_fired(), _TARGET, journey=journey)

    assert result.answered is True
    assert "idx_abc" in result.provenance  # carries the git-bound index identity as provenance
    assert "no LSP edges" in result.honest_gaps  # honest gaps carried structurally
    assert result.context
    assert "scanner" in result.context.lower()
    assert "no LSP edges" in result.context  # gaps disclosed inline, not hidden


@pytest.mark.asyncio
async def test_skipped_gate_never_calls_engine():
    called = False

    async def journey(query, target):
        nonlocal called
        called = True
        return _lens_response()

    result = await surface_code_intelligence(GateDecision(fire=False, reason="skip"), _TARGET, journey=journey)

    assert result.answered is False
    assert called is False
