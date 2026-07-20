"""Tests for intelligence integration into the runtime."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.runtime import Runtime
from core.engine.runtime.model_adapter import MockAdapter
from core.engine.runtime.models import AssistantMessage


@pytest.mark.asyncio
async def test_runtime_with_intelligence_layer():
    """Runtime should compose prompts with intelligence when available."""
    from core.engine.cognition.models import CognitiveComposition

    runtime = Runtime(
        adapter=MockAdapter(responses=["Security review complete."]),
        enable_intelligence=True,
    )
    mock_composition = CognitiveComposition(
        meta_skills=[],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    with patch.object(
        runtime._intelligence,
        "classify_compose_and_load",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = (
            {"discipline": "security", "archetype": "analyst", "mode": "deliberative", "specialties": []},
            "## Expert Knowledge\n- Always sanitize user input",
            mock_composition,
        )
        with patch.object(runtime._intelligence, "load_code_context", new_callable=AsyncMock, return_value=""):
            messages = [msg async for msg in runtime.chat("review login.py for security")]
        mock.assert_called_once()
        assistants = [m for m in messages if isinstance(m, AssistantMessage)]
        assert len(assistants) == 1


@pytest.mark.asyncio
async def test_runtime_without_intelligence():
    """Runtime should work fine with intelligence disabled."""
    runtime = Runtime(
        adapter=MockAdapter(responses=["Hello!"]),
        enable_intelligence=False,
    )
    messages = [msg async for msg in runtime.chat("hi")]
    assistants = [m for m in messages if isinstance(m, AssistantMessage)]
    assert len(assistants) == 1
    assert assistants[0].content == "Hello!"


@pytest.mark.asyncio
async def test_runtime_auto_extract_fires():
    """Auto-extraction should fire after each turn."""
    from core.engine.cognition.models import CognitiveComposition

    runtime = Runtime(
        adapter=MockAdapter(responses=["I fixed the bug."]),
        enable_intelligence=True,
    )
    mock_composition = CognitiveComposition(
        meta_skills=[],
        depth=1,
        active_phases=[],
        resolved_instruments={},
        prompt_sections=[],
        fusion_mode=True,
    )
    with patch.object(
        runtime._intelligence,
        "classify_compose_and_load",
        new_callable=AsyncMock,
    ) as mock_cl:
        mock_cl.return_value = ({"discipline": "architecture", "specialties": []}, "", mock_composition)
        with patch.object(runtime._intelligence, "load_code_context", new_callable=AsyncMock, return_value=""):
            with patch.object(runtime._extractor, "fire_and_forget") as mock_extract:
                _ = [msg async for msg in runtime.chat("fix the auth bug")]
                mock_extract.assert_called_once()
