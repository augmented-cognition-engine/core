# tests/test_adversarial_multi_round.py
"""Tests for multi-round adversarial pattern with constrained actions and convergence."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.patterns.adversarial import AdversarialPattern, _check_convergence
from core.engine.orchestration.patterns.base import PatternConfig


def _make_factory():
    factory = MagicMock()
    agent = MagicMock()
    agent.agent_id = "agent-test"
    agent.execute = AsyncMock(
        return_value=AgentResult(
            agent_id="agent-test",
            status="completed",
            output="Test output",
        )
    )
    factory.create.return_value = agent
    return factory


def _make_bus():
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


def _make_pattern():
    return AdversarialPattern(bus=_make_bus(), factory=_make_factory())


def _make_agent_configs():
    return [
        AgentConfig(role="proponent", system_prompt="Argue for."),
        AgentConfig(role="critic", system_prompt="Argue against."),
    ]


# ---------------------------------------------------------------------------
# Unit tests for _check_convergence
# ---------------------------------------------------------------------------


def test_check_convergence_empty():
    """Empty list returns False."""
    assert _check_convergence([]) is False


def test_check_convergence_all_agree():
    """All AGREE outputs → converged above threshold."""
    outputs = [
        {"output": "AGREE\nI agree with the other perspectives."},
        {"output": "AGREE\nNo further objections."},
    ]
    assert _check_convergence(outputs, threshold=0.8) is True


def test_check_convergence_all_concede():
    """All CONCEDE outputs → converged."""
    outputs = [
        {"output": "CONCEDE\nI was wrong about this point."},
        {"output": "CONCEDE\nThe evidence is convincing."},
    ]
    assert _check_convergence(outputs, threshold=0.8) is True


def test_check_convergence_mixed_below_threshold():
    """Half AGREE and half CHALLENGE → not converged at 0.8."""
    outputs = [
        {"output": "AGREE\nOK."},
        {"output": "CHALLENGE\nI disagree."},
    ]
    assert _check_convergence(outputs, threshold=0.8) is False


def test_check_convergence_mixed_above_threshold():
    """Three AGREE, one CHALLENGE → converged at 0.7 threshold."""
    outputs = [
        {"output": "AGREE\nOK."},
        {"output": "AGREE\nOK."},
        {"output": "AGREE\nOK."},
        {"output": "CHALLENGE\nI disagree."},
    ]
    assert _check_convergence(outputs, threshold=0.7) is True
    assert _check_convergence(outputs, threshold=0.8) is False


def test_check_convergence_case_insensitive():
    """Action detection is case-insensitive (uppercased internally)."""
    outputs = [
        {"output": "agree\nI accept."},
        {"output": "concede\nYou are right."},
    ]
    assert _check_convergence(outputs, threshold=0.8) is True


def test_check_convergence_strips_punctuation():
    """Trailing punctuation on action line is stripped."""
    outputs = [
        {"output": "AGREE.\nSome explanation."},
        {"output": "AGREE!\nAnother explanation."},
    ]
    assert _check_convergence(outputs, threshold=0.8) is True


# ---------------------------------------------------------------------------
# Adversarial pattern integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_round_default_behavior():
    """Default (no metadata) runs exactly 1 round of challenge, metadata.rounds == 1."""
    factory = _make_factory()
    bus = _make_bus()
    pattern = AdversarialPattern(bus=bus, factory=factory)
    config = PatternConfig(run_id="run1", product_id="product:test")

    result = await pattern.execute("Debate topic", config, _make_agent_configs())

    assert result.status == "completed"
    assert result.metadata["rounds"] == 1
    assert result.metadata["positions"] == 2
    assert result.metadata["challenges"] == 2
    # 2 independent + 2 challenge + 1 synthesis = 5 factory.create calls
    assert factory.create.call_count == 5


@pytest.mark.asyncio
async def test_multi_round_executes_multiple_challenge_phases():
    """With rounds=3, verify correct factory.create call count and metadata.rounds == 3."""
    factory = _make_factory()
    bus = _make_bus()
    pattern = AdversarialPattern(bus=bus, factory=factory)
    config = PatternConfig(run_id="run2", product_id="product:test", metadata={"rounds": 3})

    result = await pattern.execute("Debate topic", config, _make_agent_configs())

    assert result.status == "completed"
    assert result.metadata["rounds"] == 3
    assert result.metadata["positions"] == 2
    # 3 rounds × 2 agents = 6 challenge agents
    assert result.metadata["challenges"] == 6
    # 2 independent + 6 challenge + 1 synthesis = 9 factory.create calls
    assert factory.create.call_count == 9


@pytest.mark.asyncio
async def test_constrained_actions_in_challenge():
    """With constrained_actions=True, agents are created for all rounds."""
    factory = _make_factory()
    bus = _make_bus()
    pattern = AdversarialPattern(bus=bus, factory=factory)
    config = PatternConfig(
        run_id="run3",
        product_id="product:test",
        metadata={"rounds": 2, "constrained_actions": True},
    )

    result = await pattern.execute("Debate topic", config, _make_agent_configs())

    assert result.status == "completed"
    # At minimum: 2 independent + some challenge rounds + 1 synthesis >= 5
    assert factory.create.call_count >= 5
    assert result.metadata["rounds"] >= 1


@pytest.mark.asyncio
async def test_constrained_actions_prompt_contains_vocabulary():
    """With constrained_actions=True, challenge prompt includes action vocabulary."""
    factory = _make_factory()
    bus = _make_bus()
    pattern = AdversarialPattern(bus=bus, factory=factory)
    config = PatternConfig(
        run_id="run4",
        product_id="product:test",
        metadata={"rounds": 1, "constrained_actions": True},
    )

    await pattern.execute("Debate topic", config, _make_agent_configs())

    # Inspect calls to factory.create — challenge agents get a shell with constrained prompt
    # The shell's user_prompt should contain the action vocabulary instruction
    call_args_list = factory.create.call_args_list
    # Calls: 0,1 = independent; 2,3 = challenge round 1; 4 = synthesis
    challenge_call_args = call_args_list[2]
    shell = challenge_call_args[0][1]  # positional arg 1 is the shell
    assert "AGREE" in shell.user_prompt
    assert "CHALLENGE" in shell.user_prompt
    assert "CONCEDE" in shell.user_prompt


@pytest.mark.asyncio
async def test_constrained_actions_convergence_early_exit():
    """With constrained_actions=True, AGREE responses trigger early exit before all rounds."""
    factory = _make_factory()
    bus = _make_bus()

    # First round of challenges: agents AGREE → convergence → exit early
    call_count = 0

    async def execute_with_convergence(task, context=None):
        nonlocal call_count
        call_count += 1
        # Independent phase (calls 1-2) return normal output
        # Challenge phase (calls 3+) return AGREE to trigger convergence
        if call_count <= 2:
            return AgentResult(agent_id="agent-test", status="completed", output="My position.")
        elif call_count <= 4:
            return AgentResult(agent_id="agent-test", status="completed", output="AGREE\nI concur.")
        else:
            return AgentResult(agent_id="agent-test", status="completed", output="Synthesis.")

    agent = MagicMock()
    agent.agent_id = "agent-test"
    agent.execute = execute_with_convergence
    factory.create.return_value = agent

    config = PatternConfig(
        run_id="run5",
        product_id="product:test",
        # 3 rounds requested, but convergence after round 1 should stop early
        metadata={"rounds": 3, "constrained_actions": True},
    )
    pattern = AdversarialPattern(bus=bus, factory=factory)

    result = await pattern.execute("Debate topic", config, _make_agent_configs())

    assert result.status == "completed"
    # Early exit: only 1 challenge round completed (not 3)
    assert result.metadata["rounds"] < 3


@pytest.mark.asyncio
async def test_multi_round_synthesis_includes_all_rounds():
    """Synthesis prompt text is built from all round outputs, not just the last."""
    factory = _make_factory()
    bus = _make_bus()

    round_outputs = []

    async def capture_execute(task, context=None):
        round_outputs.append(task)
        return AgentResult(agent_id="agent-test", status="completed", output="Round output.")

    agent = MagicMock()
    agent.agent_id = "agent-test"
    agent.execute = capture_execute
    factory.create.return_value = agent

    config = PatternConfig(
        run_id="run6",
        product_id="product:test",
        metadata={"rounds": 2},
    )
    pattern = AdversarialPattern(bus=bus, factory=factory)

    await pattern.execute("Debate topic", config, _make_agent_configs())

    # The last call is the synthesis — its prompt should reference round headers
    synthesis_prompt = round_outputs[-1]
    assert "Round 1" in synthesis_prompt or "round_1" in synthesis_prompt.lower()


@pytest.mark.asyncio
async def test_multi_round_metadata_challenges_count():
    """metadata.challenges is the total across all rounds (not just the last)."""
    factory = _make_factory()
    bus = _make_bus()
    pattern = AdversarialPattern(bus=bus, factory=factory)
    config = PatternConfig(
        run_id="run7",
        product_id="product:test",
        metadata={"rounds": 4},
    )

    result = await pattern.execute("Debate topic", config, _make_agent_configs())

    # 4 rounds × 2 agents = 8 total challenge outputs
    assert result.metadata["challenges"] == 8
    assert result.metadata["rounds"] == 4
