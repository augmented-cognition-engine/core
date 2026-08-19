"""Validate surface_code_intelligence against the REAL AtriumCodeLensV1Alpha1 serialization.

The surface unit tests use an assumed response dict; this builds a real lens via the contract models
and ``model_dump``s it to the exact shape the HTTP client receives — catching field-name/shape
assumptions. Notably, a real lens routinely carries its value in ``impact`` (direct dependents,
affected tests, coverage gaps) with **empty** ``nodes`` — so a surface that keys "has content" on
nodes alone would wrongly refuse to answer a perfectly good projection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace_mcp_client.ambient import GateDecision, surface_code_intelligence
from core.engine.code_intelligence.contracts import (
    AtriumCodeLensV1Alpha1,
    ChangeImpactV1Alpha1,
    ConfidenceBand,
    RepositoryIndexIdentityV1Alpha1,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)
_TARGET = "core/engine/api/main.py"


def _real_lens() -> AtriumCodeLensV1Alpha1:
    index = RepositoryIndexIdentityV1Alpha1(
        repository="ace-core",
        revision="1" * 40,
        dirty=False,
        working_tree_digest="clean",
        scanner_contract="ace.graph-builder/phase1",
        observed_languages=("python",),
        generated_at=_NOW - timedelta(minutes=5),
    )
    return AtriumCodeLensV1Alpha1(
        index=index,
        query="What depends on this API module?",
        target_path=_TARGET,
        nodes=(),
        edges=(),
        impact=ChangeImpactV1Alpha1(
            target_path=_TARGET,
            direct_dependents=("tests/test_main.py",),
            transitive_dependents=(),
            affected_tests=("tests/test_main.py",),
            known_coverage_gaps=("runtime registration",),
            confidence=ConfidenceBand.SUPPORTED,
            basis="Static import graph only.",
        ),
        disconnected_symbols=(),
        evidence=(),
        omissions=("source bodies intentionally excluded",),
        degraded_reasons=(),
    )


def _response_dict() -> dict:
    return {
        "lens": _real_lens().model_dump(mode="json"),
        "index_snapshot_id": "idx_snap_abc123",
        "index_generation": 1,
        "limitations": ["tree-sitter structure only"],
    }


@pytest.mark.asyncio
async def test_surface_answers_a_real_impact_only_lens():
    async def journey(query, target):
        return _response_dict()

    decision = GateDecision(fire=True, reason="test", query="what depends on main.py?")
    result = await surface_code_intelligence(decision, _TARGET, journey=journey)

    assert result.answered is True, "a real lens with impact but empty nodes must still answer"
    assert "idx_snap_abc123" in result.provenance
    assert "tests/test_main.py" in result.context  # the useful impact content is surfaced
    assert "source bodies intentionally excluded" in result.honest_gaps  # lens omissions
    assert "runtime registration" in result.honest_gaps  # impact coverage gaps
