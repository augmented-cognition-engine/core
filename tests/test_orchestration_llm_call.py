from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_multiphase_system_prompt_has_cache_structure():
    """Multiphase executor should split system prompt for cache optimization."""
    from core.engine.cognition.models import CognitiveComposition, RecipePhase
    from core.engine.cognition.multiphase import MultiPhaseExecutor

    captured_system = []

    async def mock_llm_call(system_prompt, user_prompt):
        captured_system.append(system_prompt)
        return '{"output": "test", "confidence": 0.8, "evidence": [], "gaps": []}'

    phase = RecipePhase(
        cognitive_function="analysis",
        instruments=[],
        min_depth=1,
        output_schema="structured analysis",
    )
    composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=3,
        active_phases=[phase],
        resolved_instruments={"0": []},
        fusion_mode=False,
        prompt_sections=[
            {
                "fusion_label": "[ANALYSIS]",
                "cognitive_function": "analysis",
                "output_schema": "structured analysis",
                "framework_slugs": ["test-framework"],
            }
        ],
    )

    executor = MultiPhaseExecutor(llm_call=mock_llm_call)
    await executor.execute("test task", composition, {"test-framework": "Use this framework."})

    # System prompt was captured
    assert len(captured_system) >= 1
    system = captured_system[0]
    # Should be a list (cache-structured) not a plain string
    assert isinstance(system, list), f"Expected list for cache_control, got {type(system)}"
    # First block should have cache_control
    assert system[0].get("cache_control") == {"type": "ephemeral"}
    # Second block should be the dynamic suffix (no cache_control)
    assert "cache_control" not in system[1]


@pytest.mark.asyncio
async def test_llm_call_passes_system_and_user_separately():
    """The _llm_call bridge should pass system via system= and user via prompt=."""
    from core.engine.core.llm import ClaudeProvider

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="phase output")]
    mock_response.usage = None

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = AsyncMock()
    provider._client.messages.create = AsyncMock(return_value=mock_response)
    provider._default_model = "claude-sonnet-4-6"

    # Simulate the fixed _llm_call pattern
    result = await provider.complete(
        "Analyze this task",
        system="You are executing the [FRAME] phase.",
        model="claude-sonnet-4-6",
    )

    assert result == "phase output"
    call_kwargs = provider._client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "You are executing the [FRAME] phase."
    assert call_kwargs["messages"][0]["content"] == "Analyze this task"
