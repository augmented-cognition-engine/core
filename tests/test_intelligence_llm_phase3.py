# tests/test_intelligence_llm_phase3.py
"""Tests for Phase 3 three-tier LLM analysis."""

import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.intelligence.graph_builder import GraphBuilder
from core.engine.runtime.models import AssistantMessage


def _test_repo():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "auth.py"), "w") as f:
        f.write("import jwt\n\ndef validate_token(token: str) -> bool:\n    return jwt.decode(token) is not None\n")
    return d


def _mock_adapter(result_dict):
    """Create a mock adapter that returns JSON."""
    adapter = AsyncMock()

    async def fake_call_model(*args, **kwargs):
        yield AssistantMessage(content=json.dumps(result_dict), model="mock")

    adapter.call_model = fake_call_model
    return adapter


@pytest.mark.asyncio
async def test_phase3a_analyzes_files():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    mock_result = {
        "purpose": "JWT token validation",
        "discipline": "security",
        "quality_risks": ["No expiry check"],
        "key_exports": ["validate_token"],
        "architectural_role": "Authentication gate",
    }

    with patch("core.engine.runtime.model_adapter.ClaudeAdapter") as MockCls:
        MockCls.return_value = _mock_adapter(mock_result)
        stats = await builder._phase3a_file_analysis()
        assert stats["analyzed"] >= 1

        analyzed = [f for f in builder.get_files() if f.get("analysis")]
        assert len(analyzed) >= 1
        assert analyzed[0]["analysis"]["discipline"] == "security"


@pytest.mark.asyncio
async def test_phase3a_validates_schema():
    """Invalid JSON triggers retry, not immediate failure."""
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    # Missing required key — should retry
    incomplete_result = {"purpose": "test"}
    complete_result = {
        "purpose": "test",
        "discipline": "testing",
        "quality_risks": [],
        "key_exports": [],
        "architectural_role": "test",
    }

    call_count = 0

    async def fake_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield AssistantMessage(content=json.dumps(incomplete_result), model="mock")
        else:
            yield AssistantMessage(content=json.dumps(complete_result), model="mock")

    mock_adapter = AsyncMock()
    mock_adapter.call_model = fake_call

    with patch("core.engine.runtime.model_adapter.ClaudeAdapter") as MockCls:
        MockCls.return_value = mock_adapter
        stats = await builder._phase3a_file_analysis()
        assert stats["retried"] >= 1


@pytest.mark.asyncio
async def test_phase3a_skips_tiny_files():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "empty.py"), "w") as f:
        f.write("# tiny\n")

    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    with patch("core.engine.runtime.model_adapter.ClaudeAdapter"):
        stats = await builder._phase3a_file_analysis()
        assert stats["skipped"] >= 1


@pytest.mark.asyncio
async def test_phase3b_groups_by_module():
    d = tempfile.mkdtemp()
    mod = os.path.join(d, "engine", "auth")
    os.makedirs(mod)
    for name in ["validate.py", "tokens.py", "middleware.py"]:
        with open(os.path.join(mod, name), "w") as f:
            f.write(
                f"def {name.replace('.py', '')}():\n    pass\n    # padding content for min size\n    # more content\n"
            )

    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    # Manually set analysis on files (simulating Phase 3a)
    for f in builder._files:
        f["analysis"] = {
            "purpose": f"Does {f['path']}",
            "discipline": "security",
            "quality_risks": ["test risk"],
        }

    mock_synthesis = {
        "purpose": "Authentication module",
        "key_files": ["validate.py"],
        "internal_patterns": ["middleware"],
        "quality_gaps": [],
        "dependencies": [],
        "risk_summary": "low",
    }

    with patch("core.engine.intelligence.graph_builder.get_llm") as mock_llm:
        llm_instance = AsyncMock()
        llm_instance.complete_json = AsyncMock(return_value=mock_synthesis)
        mock_llm.return_value = llm_instance

        stats = await builder._phase3b_module_synthesis()
        assert stats["modules"] >= 1
        assert "engine/auth" in builder._module_summaries
