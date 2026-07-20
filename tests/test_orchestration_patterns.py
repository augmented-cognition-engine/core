# tests/test_orchestration_patterns.py
"""Unit tests for all 5 orchestration patterns with MockLLMProvider."""

import pytest

from core.engine.orchestration.agent import AgentConfig
from core.engine.orchestration.bus import OrchestrationBus
from core.engine.orchestration.factory import AgentFactory
from core.engine.orchestration.patterns.adversarial import AdversarialPattern
from core.engine.orchestration.patterns.base import PatternConfig
from core.engine.orchestration.patterns.fanout import FanOutPattern
from core.engine.orchestration.patterns.independent import IndependentPattern
from core.engine.orchestration.patterns.pipeline import PipelinePattern
from core.engine.orchestration.patterns.team import TeamPattern
from core.engine.orchestration.testing import MockLLMProvider


def _make_env(responses=None):
    """Create bus + factory with mock LLM."""
    llm = MockLLMProvider(responses=responses)
    bus = OrchestrationBus()
    factory = AgentFactory(llm_provider=llm, bus=bus)
    config = PatternConfig(run_id="test_run", product_id="product:test")
    return bus, factory, config, llm


# ---------------------------------------------------------------------------
# Independent (Pattern A)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_independent_single_agent():
    bus, factory, config, llm = _make_env({"Task:": "Done!"})
    pattern = IndependentPattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Do something",
        config,
        [AgentConfig(role="executor", system_prompt="You are an executor.")],
    )
    assert result.status == "completed"
    assert result.pattern_name == "independent"
    assert len(result.agent_results) == 1


@pytest.mark.asyncio
async def test_independent_no_system_prompt():
    """Independent pattern works without a system_prompt on the AgentConfig."""
    bus, factory, config, llm = _make_env()
    pattern = IndependentPattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Do something",
        config,
        [AgentConfig(role="executor")],
    )
    assert result.status == "completed"
    assert len(result.agent_results) == 1


@pytest.mark.asyncio
async def test_independent_empty_configs():
    """Independent pattern creates default executor when configs list is empty."""
    bus, factory, config, llm = _make_env()
    pattern = IndependentPattern(bus=bus, factory=factory)
    result = await pattern.execute("Do something", config, [])
    assert result.status == "completed"


# ---------------------------------------------------------------------------
# Pipeline (Pattern C)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_sequential():
    bus, factory, config, llm = _make_env({"Task:": "Step output"})
    pattern = PipelinePattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Write a report",
        config,
        [
            AgentConfig(role="researcher", system_prompt="Research the topic."),
            AgentConfig(role="writer", system_prompt="Write the report."),
        ],
    )
    assert result.status == "completed"
    assert result.pattern_name == "pipeline"
    assert len(result.agent_results) == 2


@pytest.mark.asyncio
async def test_pipeline_empty_configs_fails():
    """Pipeline with no agent configs fails."""
    bus, factory, config, _ = _make_env()
    pattern = PipelinePattern(bus=bus, factory=factory)
    result = await pattern.execute("Write a report", config, [])
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_pipeline_single_agent():
    """Pipeline with a single agent still works."""
    bus, factory, config, llm = _make_env()
    pattern = PipelinePattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Do it",
        config,
        [AgentConfig(role="solo", system_prompt="Just do it.")],
    )
    assert result.status == "completed"
    assert len(result.agent_results) == 1


@pytest.mark.asyncio
async def test_pipeline_publishes_handoff_events():
    """Pipeline emits HANDOFF messages on the bus between steps."""
    bus, factory, config, llm = _make_env()
    pattern = PipelinePattern(bus=bus, factory=factory)
    await pattern.execute(
        "Report",
        config,
        [
            AgentConfig(role="researcher", system_prompt="Research."),
            AgentConfig(role="writer", system_prompt="Write."),
        ],
    )
    # Check the bus message log for HANDOFF
    from core.engine.orchestration.bus import MessageType

    handoffs = bus.get_messages("test_run", message_type=MessageType.HANDOFF)
    assert len(handoffs) == 1


# ---------------------------------------------------------------------------
# Adversarial (Pattern D)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adversarial_three_phases():
    bus, factory, config, llm = _make_env({"": "Output"})
    pattern = AdversarialPattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Debate topic",
        config,
        [
            AgentConfig(role="proponent", system_prompt="Argue for."),
            AgentConfig(role="critic", system_prompt="Argue against."),
        ],
    )
    assert result.status == "completed"
    assert result.pattern_name == "adversarial"
    # 2 independent + 2 challenge + 1 synthesis = 5 agent results
    assert len(result.agent_results) == 5


@pytest.mark.asyncio
async def test_adversarial_needs_two_agents():
    bus, factory, config, _ = _make_env()
    pattern = AdversarialPattern(bus=bus, factory=factory)
    result = await pattern.execute("Debate", config, [AgentConfig(role="solo")])
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_adversarial_metadata():
    """Adversarial pattern populates positions/challenges in metadata."""
    bus, factory, config, llm = _make_env({"": "Output"})
    pattern = AdversarialPattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Debate",
        config,
        [
            AgentConfig(role="a", system_prompt="Side A"),
            AgentConfig(role="b", system_prompt="Side B"),
        ],
    )
    assert result.metadata.get("positions") == 2
    assert result.metadata.get("challenges") == 2


# ---------------------------------------------------------------------------
# FanOut (Pattern E)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fanout_parallel():
    bus, factory, config, llm = _make_env({"Task:": "Result"})
    pattern = FanOutPattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Research parallel",
        config,
        [
            AgentConfig(role="researcher", system_prompt="Research aspect A."),
            AgentConfig(role="researcher", system_prompt="Research aspect B."),
            AgentConfig(role="researcher", system_prompt="Research aspect C."),
        ],
    )
    assert result.status == "completed"
    assert result.pattern_name == "fanout"
    assert result.metadata.get("total_agents") == 3


@pytest.mark.asyncio
async def test_fanout_empty_configs_fails():
    """FanOut with no configs fails."""
    bus, factory, config, _ = _make_env()
    pattern = FanOutPattern(bus=bus, factory=factory)
    result = await pattern.execute("Research", config, [])
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_fanout_single_agent():
    """FanOut with a single agent works."""
    bus, factory, config, llm = _make_env()
    pattern = FanOutPattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Research",
        config,
        [AgentConfig(role="researcher", system_prompt="Research.")],
    )
    assert result.status == "completed"
    assert result.metadata.get("successful") == 1


@pytest.mark.asyncio
async def test_fanout_spawned_messages():
    """FanOut publishes AGENT_SPAWNED messages for each agent."""
    from core.engine.orchestration.bus import MessageType

    bus, factory, config, llm = _make_env()
    pattern = FanOutPattern(bus=bus, factory=factory)
    await pattern.execute(
        "Research",
        config,
        [
            AgentConfig(role="r", system_prompt="R1."),
            AgentConfig(role="r", system_prompt="R2."),
        ],
    )
    spawned = bus.get_messages("test_run", message_type=MessageType.AGENT_SPAWNED)
    assert len(spawned) == 2


# ---------------------------------------------------------------------------
# Team (Pattern B)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_team_concurrent_with_synthesis():
    bus, factory, config, llm = _make_env({"": "Team output"})
    pattern = TeamPattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Solve collaboratively",
        config,
        [
            AgentConfig(role="backend", system_prompt="Handle backend."),
            AgentConfig(role="frontend", system_prompt="Handle frontend."),
        ],
    )
    assert result.status == "completed"
    assert result.pattern_name == "team"
    # 2 team + 1 synthesis = 3
    assert len(result.agent_results) == 3


@pytest.mark.asyncio
async def test_team_needs_two_agents():
    bus, factory, config, _ = _make_env()
    pattern = TeamPattern(bus=bus, factory=factory)
    result = await pattern.execute("Solo", config, [AgentConfig(role="solo")])
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_team_metadata():
    """Team pattern populates team_size and successful count in metadata."""
    bus, factory, config, llm = _make_env({"": "Output"})
    pattern = TeamPattern(bus=bus, factory=factory)
    result = await pattern.execute(
        "Task",
        config,
        [
            AgentConfig(role="a", system_prompt="Agent A."),
            AgentConfig(role="b", system_prompt="Agent B."),
        ],
    )
    assert result.metadata.get("team_size") == 2
    assert result.metadata.get("successful") == 2


@pytest.mark.asyncio
async def test_team_spawned_messages():
    """Team publishes AGENT_SPAWNED messages for each team member plus synthesizer."""
    from core.engine.orchestration.bus import MessageType

    bus, factory, config, llm = _make_env({"": "Output"})
    pattern = TeamPattern(bus=bus, factory=factory)
    await pattern.execute(
        "Task",
        config,
        [
            AgentConfig(role="a", system_prompt="A."),
            AgentConfig(role="b", system_prompt="B."),
        ],
    )
    spawned = bus.get_messages("test_run", message_type=MessageType.AGENT_SPAWNED)
    # 2 team agents + 1 synthesizer = 3
    assert len(spawned) == 3
