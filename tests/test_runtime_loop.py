"""Tests for the core query loop."""

import pytest

from core.engine.runtime.model_adapter import MockAdapter
from core.engine.runtime.models import (
    AssistantMessage,
    ToolResultMessage,
    ToolUseBlock,
    UserMessage,
)
from core.engine.runtime.query_loop import QueryParams, query_loop
from core.engine.runtime.tool_executor import ToolExecutor
from core.engine.runtime.tools import ToolRegistry
from core.engine.runtime.tools.bash import BashTool


def _make_params(adapter, registry=None, **overrides) -> QueryParams:
    if registry is None:
        registry = ToolRegistry()
        registry.register(BashTool())
    executor = ToolExecutor(registry)
    return QueryParams(
        system="You are helpful.",
        messages=[UserMessage(content="hello")],
        adapter=adapter,
        executor=executor,
        tool_schemas=registry.list_schemas(),
        **overrides,
    )


@pytest.mark.asyncio
async def test_simple_response():
    adapter = MockAdapter(responses=["Hello!"])
    params = _make_params(adapter)
    messages = [msg async for msg in query_loop(params)]
    assistants = [m for m in messages if isinstance(m, AssistantMessage)]
    assert len(assistants) == 1
    assert assistants[0].content == "Hello!"


@pytest.mark.asyncio
async def test_tool_use_loop():
    """Model requests tool -> tool executes -> result fed back -> model responds."""
    tool_use = ToolUseBlock(id="tu_1", name="bash", input={"command": "echo done"})
    adapter = MockAdapter(
        responses=[
            AssistantMessage(content="Let me run that.", model="mock", tool_use=[tool_use]),
            "The command output: done",
        ]
    )
    params = _make_params(adapter)
    messages = [msg async for msg in query_loop(params)]
    assistants = [m for m in messages if isinstance(m, AssistantMessage)]
    assert len(assistants) == 2
    assert "done" in assistants[1].content


@pytest.mark.asyncio
async def test_multi_tool_use():
    """Model returns 2 tool_use blocks — both execute, results grouped correctly."""
    tool_uses = [
        ToolUseBlock(id="tu_1", name="bash", input={"command": "echo first"}),
        ToolUseBlock(id="tu_2", name="bash", input={"command": "echo second"}),
    ]
    adapter = MockAdapter(
        responses=[
            AssistantMessage(content="Running both.", model="mock", tool_use=tool_uses),
            "Both commands ran.",
        ]
    )
    params = _make_params(adapter)
    messages = [msg async for msg in query_loop(params)]
    tool_results = [m for m in messages if isinstance(m, ToolResultMessage)]
    assert len(tool_results) == 2
    assert tool_results[0].tool_use_id == "tu_1"
    assert tool_results[1].tool_use_id == "tu_2"
    assistants = [m for m in messages if isinstance(m, AssistantMessage)]
    assert len(assistants) == 2


@pytest.mark.asyncio
async def test_max_turns():
    """Loop should stop after max_turns."""
    tool_use = ToolUseBlock(id="tu_1", name="bash", input={"command": "echo x"})
    adapter = MockAdapter(
        responses=[
            AssistantMessage(content="again", model="mock", tool_use=[tool_use]),
        ]
        * 5
    )
    params = _make_params(adapter, max_turns=3)
    messages = [msg async for msg in query_loop(params)]
    assistants = [m for m in messages if isinstance(m, AssistantMessage)]
    assert len(assistants) <= 3


@pytest.mark.asyncio
async def test_query_loop_stream_yields_thinking_and_text_chunks():
    from core.engine.runtime.events import ThinkingDelta
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.models import AssistantMessage, UserMessage
    from core.engine.runtime.query_loop import QueryParams, query_loop
    from core.engine.runtime.tool_executor import ToolExecutor
    from core.engine.runtime.tools import ToolRegistry

    adapter = MockAdapter(responses=["hello world"])
    params = QueryParams(
        system="test",
        messages=[UserMessage(content="hi")],
        adapter=adapter,
        executor=ToolExecutor(ToolRegistry()),
        stream=True,
    )
    items = []
    async for item in query_loop(params):
        items.append(item)

    thinking = [i for i in items if isinstance(i, ThinkingDelta)]
    text = [i for i in items if isinstance(i, str)]
    final = [i for i in items if isinstance(i, AssistantMessage)]

    assert len(thinking) >= 1
    assert len(text) >= 1
    assert len(final) == 1


@pytest.mark.asyncio
async def test_query_loop_stream_false_unchanged():
    """Non-streaming path still yields only Message objects."""
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.models import AssistantMessage, UserMessage
    from core.engine.runtime.query_loop import QueryParams, query_loop
    from core.engine.runtime.tool_executor import ToolExecutor
    from core.engine.runtime.tools import ToolRegistry

    adapter = MockAdapter(responses=["hello"])
    params = QueryParams(
        system="test",
        messages=[UserMessage(content="hi")],
        adapter=adapter,
        executor=ToolExecutor(ToolRegistry()),
        stream=False,
    )
    items = []
    async for item in query_loop(params):
        items.append(item)

    assert all(isinstance(i, AssistantMessage) for i in items)


@pytest.mark.asyncio
async def test_runtime_chat_yields_intelligence_loaded_when_enabled():
    """IntelligenceLoadedMessage is yielded before query_loop when intelligence is on."""
    from unittest.mock import AsyncMock, MagicMock

    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.models import IntelligenceLoadedMessage
    from core.engine.runtime.runtime import Runtime

    adapter = MockAdapter(responses=["done"])
    runtime = Runtime(adapter=adapter, enable_intelligence=False)

    # Manually inject a mock intelligence layer
    mock_intel = MagicMock()
    mock_composition = MagicMock()
    mock_composition.meta_skills = []
    mock_intel.classify_compose_and_load = AsyncMock(
        return_value=({"discipline": "testing", "specialties": []}, "context text", mock_composition)
    )
    mock_intel.load_code_context = AsyncMock(return_value=None)
    mock_intel.load_insights = AsyncMock(return_value=[])
    runtime._intelligence = mock_intel

    items = []
    async for msg in runtime.chat("run tests"):
        items.append(msg)

    intel_msgs = [m for m in items if isinstance(m, IntelligenceLoadedMessage)]
    assert len(intel_msgs) == 1
    assert intel_msgs[0].entries == [("testing", 1)]


@pytest.mark.asyncio
async def test_runtime_chat_stream_false_no_chunks():
    """stream=False still yields only Message objects (no str or ThinkingDelta)."""
    from core.engine.runtime.events import ThinkingDelta
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    adapter = MockAdapter(responses=["hello"])
    runtime = Runtime(adapter=adapter, enable_intelligence=False)
    items = []
    async for msg in runtime.chat("hi", stream=False):
        items.append(msg)

    assert not any(isinstance(i, (str, ThinkingDelta)) for i in items)


# ---------------------------------------------------------------------------
# _assemble_system_prompt: framework content injection
# ---------------------------------------------------------------------------


from core.engine.cognition.fusion import FALLBACK_SENTINEL
from core.engine.cognition.models import CognitiveComposition, InstrumentSpec, RecipePhase
from core.engine.runtime.runtime import Runtime

DEMO_PROMPT = (
    "When I encounter a problem that resists clear analysis, the first thing I do is ask: "
    "what is the complete space? I'm not mapping a solution — I'm building the territory."
)


def _composition_with_slug(slug: str) -> CognitiveComposition:
    phase = RecipePhase(
        cognitive_function="frame",
        instruments=[InstrumentSpec(slug=slug, fallback_slug=slug)],
        min_depth=1,
        output_schema="framing",
        pattern="solo",
    )
    return CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=1,
        active_phases=[phase],
        resolved_instruments={"0": [slug]},
        prompt_sections=[
            {
                "phase_idx": "0",
                "cognitive_function": "frame",
                "framework_slugs": [slug],
                "output_schema": "framing",
                "pattern": "solo",
                "fusion_label": "[FRAME]",
            }
        ],
        fusion_mode=True,
    )


def test_assemble_system_prompt_injects_framework_content():
    """When framework_prompts are available, full demo-mode content appears; sentinel absent."""
    rt = Runtime.__new__(Runtime)
    rt._system = "You are ACE."
    composition = _composition_with_slug("first-principles")

    result = rt._assemble_system_prompt(
        classification={"archetype": "analyst", "mode": "deliberative", "discipline": "api_design"},
        composition=composition,
        framework_prompts={"first-principles": DEMO_PROMPT},
    )

    assert FALLBACK_SENTINEL not in result, "Sentinel fired even with framework_prompts populated"
    assert DEMO_PROMPT in result, "Demo-mode framework content not in system prompt"
    assert "[FRAME]" in result
    assert "## Cognitive Structure" in result


def test_assemble_system_prompt_fallback_to_labels_when_no_prompts():
    """When framework_prompts is empty, phase-label fallback is used (no sentinel in this path)."""
    rt = Runtime.__new__(Runtime)
    rt._system = "You are ACE."
    composition = _composition_with_slug("first-principles")

    result = rt._assemble_system_prompt(
        classification={"archetype": "analyst", "mode": "deliberative", "discipline": "api_design"},
        composition=composition,
        framework_prompts={},
    )

    # Fallback path: labels only — no framework content, but also no PromptFusion sentinel
    # (PromptFusion is not called in this path)
    assert "## Reasoning Structure" in result
    assert DEMO_PROMPT not in result


def test_assemble_system_prompt_meta_tag_embedded_in_header():
    """meta-skills tag must appear in the ## Cognitive Structure header line."""
    rt = Runtime.__new__(Runtime)
    rt._system = "You are ACE."
    composition = _composition_with_slug("first-principles")

    result = rt._assemble_system_prompt(
        classification={"archetype": "analyst", "mode": "deliberative", "complexity": "moderate"},
        composition=composition,
        framework_prompts={"first-principles": DEMO_PROMPT},
    )

    assert "## Cognitive Structure  (" in result
    assert "coding_intelligence" in result
    # Only one ## Cognitive Structure header
    assert result.count("## Cognitive Structure") == 1
