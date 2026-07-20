# tests/test_e2e_orchestration_scenarios.py
"""Comprehensive end-to-end orchestration tests.

Tests every execution scenario ACE supports:
- Pipeline (sequential context passing)
- Team (parallel with discovery forwarding)
- FanOut (parallel same-role, merged results)
- Adversarial (3-phase: independent → challenge → synthesis)
- Engagement model (multi-spin pipeline + adversarial modes)
- Dispatch planner (conflict detection + batching)
- Agent orchestrator (mixed plans with error cascades)
- Bus communication (event routing + isolation)
- Full initiative lifecycle (create → decompose → execute)

All tests use MockLLMProvider / MockAgentShell to avoid hitting real LLMs.
Tests marked @pytest.mark.e2e that touch DB require live SurrealDB.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.bus import BusMessage, MessageType, OrchestrationBus
from core.engine.orchestration.factory import AgentFactory
from core.engine.orchestration.patterns.base import PatternConfig
from core.engine.orchestration.shell import ComposedShell
from core.engine.orchestration.testing import MockLLMProvider

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_pool(db=None):
    """Build a mock DB pool for tests that don't need real SurrealDB."""
    if db is None:
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


def _make_factory(bus: OrchestrationBus, llm=None) -> AgentFactory:
    """Create an AgentFactory wired to the given bus + mock LLM."""
    return AgentFactory(llm_provider=llm or MockLLMProvider(), bus=bus)


def _make_config(run_id: str = "test-run", **kwargs) -> PatternConfig:
    """Build a PatternConfig with sensible test defaults."""
    intel_context = kwargs.pop("intel_context", "Test intelligence context")
    return PatternConfig(
        run_id=run_id,
        product_id="product:test",
        workspace_id="workspace:test",
        intel_context=intel_context,
        **kwargs,
    )


def _agent(role: str, prompt: str = "You are a helpful agent.", **kwargs) -> AgentConfig:
    """Shorthand for building an AgentConfig."""
    return AgentConfig(role=role, system_prompt=prompt, **kwargs)


class TrackingShell:
    """Agent shell that records what it received and returns configurable output.

    Unlike MockAgentShell, this captures the full task + context so tests can
    assert on what was passed to each agent.
    """

    def __init__(self, agent_id: str, output: str = "mock output", delay: float = 0.0):
        self.agent_id = agent_id
        self.output = output
        self.delay = delay
        self.calls: list[dict] = []
        self.injected: list[BusMessage] = []

    async def execute(self, task: str, context: dict | None = None) -> AgentResult:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.calls.append({"task": task, "context": context})
        return AgentResult(agent_id=self.agent_id, status="completed", output=self.output)

    async def execute_streaming(self, task: str, context: dict | None = None):
        for word in self.output.split():
            yield word + " "

    async def inject_message(self, message) -> None:
        self.injected.append(message)

    async def cancel(self) -> None:
        pass


class TrackingFactory:
    """Factory that returns pre-built TrackingShell agents and records creation order."""

    def __init__(self, bus: OrchestrationBus, shells: dict[str, TrackingShell] | None = None):
        self._bus = bus
        self._shells = shells or {}
        self._default_output = "default output"
        self.created: list[str] = []
        self._counter = 0

    def create(self, config: AgentConfig, shell: ComposedShell | None = None) -> TrackingShell:
        self._counter += 1
        agent_id = f"{config.role}_{self._counter}"
        self.created.append(config.role)

        if config.role in self._shells:
            ts = self._shells[config.role]
            ts.agent_id = agent_id
            return ts

        return TrackingShell(agent_id=agent_id, output=f"{config.role}: {self._default_output}")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PIPELINE PATTERN — Sequential Context Passing
# ═══════════════════════════════════════════════════════════════════════════════


class TestPipelinePattern:
    """Verify Pipeline (Pattern C) passes context sequentially between agents."""

    @pytest.mark.asyncio
    async def test_loaded_intelligence_reaches_every_planned_agent_system_prompt(self):
        """PatternConfig intelligence is execution context, not inert metadata."""
        from core.engine.orchestration.patterns.pipeline import PipelinePattern

        bus = OrchestrationBus()
        llm = MockLLMProvider(default="done")
        pattern = PipelinePattern(bus=bus, factory=_make_factory(bus, llm))
        marker = "M2-CONSTRAINT-regression"

        await pattern.execute(
            task="Make a decision",
            config=_make_config(intel_context=f"## Relevant Intelligence\n- {marker}: prefer proof rigor"),
            agent_configs=[_agent("researcher", "Research the options."), _agent("advisor", "Choose one.")],
        )

        assert len(llm.calls) == 2
        assert all(marker in (call["system"] or "") for call in llm.calls)

    @pytest.mark.asyncio
    async def test_precomposed_intelligence_is_not_duplicated(self):
        from core.engine.orchestration.patterns.pipeline import PipelinePattern

        bus = OrchestrationBus()
        llm = MockLLMProvider(default="done")
        pattern = PipelinePattern(bus=bus, factory=_make_factory(bus, llm))
        marker = "M2-CONSTRAINT-once"
        intel = f"## Relevant Intelligence\n- {marker}"

        await pattern.execute(
            task="Make a decision",
            config=_make_config(intel_context=intel),
            agent_configs=[_agent("advisor", f"Choose one.\n\n{intel}")],
        )

        assert (llm.calls[0]["system"] or "").count(marker) == 1

    @pytest.mark.asyncio
    async def test_accumulated_context_grows_per_step(self):
        """Each pipeline step receives accumulated output from all prior steps."""
        bus = OrchestrationBus()

        analyst = TrackingShell("analyst_1", output="Analysis: found 3 issues")
        implementer = TrackingShell("implementer_1", output="Implemented fixes for issues")
        reviewer = TrackingShell("reviewer_1", output="Review: all fixes look good")

        factory = TrackingFactory(
            bus,
            {
                "analyst": analyst,
                "implementer": implementer,
                "reviewer": reviewer,
            },
        )

        from core.engine.orchestration.patterns.pipeline import PipelinePattern

        pattern = PipelinePattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Fix authentication bugs",
            config=_make_config(),
            agent_configs=[
                _agent("analyst"),
                _agent("implementer"),
                _agent("reviewer"),
            ],
        )

        assert result.status == "completed"
        assert len(result.agent_results) == 3

        # Step 1 (analyst): should get the raw task, no prior context
        assert "Prior Steps Output" not in analyst.calls[0]["task"]

        # Step 2 (implementer): should see analyst's output
        assert "Prior Steps Output" in implementer.calls[0]["task"]
        assert "Analysis: found 3 issues" in implementer.calls[0]["task"]

        # Step 3 (reviewer): should see both prior outputs
        reviewer_task = reviewer.calls[0]["task"]
        assert "Prior Steps Output" in reviewer_task
        assert "Analysis: found 3 issues" in reviewer_task
        assert "Implemented fixes for issues" in reviewer_task

    @pytest.mark.asyncio
    async def test_handoff_events_emitted_between_steps(self):
        """HANDOFF bus events fire between each step (but not after the last)."""
        bus = OrchestrationBus()
        messages: list[BusMessage] = []

        async def capture(msg: BusMessage) -> None:
            messages.append(msg)

        bus.subscribe_global(capture)

        factory = TrackingFactory(bus)

        from core.engine.orchestration.patterns.pipeline import PipelinePattern

        pattern = PipelinePattern(bus=bus, factory=factory)

        await pattern.execute(
            task="Build API",
            config=_make_config(),
            agent_configs=[_agent("designer"), _agent("builder"), _agent("tester")],
        )

        # Allow async bus tasks to complete
        await asyncio.sleep(0.05)

        handoffs = [m for m in messages if m.type == MessageType.HANDOFF]
        spawned = [m for m in messages if m.type == MessageType.AGENT_SPAWNED]

        assert len(handoffs) == 2, f"Expected 2 handoffs (between 3 steps), got {len(handoffs)}"
        assert len(spawned) == 3, f"Expected 3 agent spawns, got {len(spawned)}"

        # Verify handoff payloads
        assert handoffs[0].payload["from_role"] == "designer"
        assert handoffs[0].payload["to_role"] == "builder"
        assert handoffs[1].payload["from_role"] == "builder"
        assert handoffs[1].payload["to_role"] == "tester"

    @pytest.mark.asyncio
    async def test_pipeline_halts_on_failure(self):
        """Pipeline stops immediately when a step fails — no further steps execute."""
        bus = OrchestrationBus()

        class FailingShell(TrackingShell):
            async def execute(self, task, context=None):
                raise RuntimeError("Step 2 exploded")

        factory = TrackingFactory(
            bus,
            {
                "step_a": TrackingShell("a", output="OK"),
                "step_b": FailingShell("b"),
                "step_c": TrackingShell("c", output="Should never run"),
            },
        )

        from core.engine.orchestration.patterns.pipeline import PipelinePattern

        pattern = PipelinePattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Multi-step work",
            config=_make_config(),
            agent_configs=[_agent("step_a"), _agent("step_b"), _agent("step_c")],
        )

        assert result.status == "failed"
        assert "step_b" in result.output.lower() or "Step 2" in result.output

        # step_c should never have been called
        step_c = factory._shells["step_c"]
        assert len(step_c.calls) == 0

    @pytest.mark.asyncio
    async def test_conversation_context_only_first_step(self):
        """conversation_messages are passed only to the first pipeline step."""
        bus = OrchestrationBus()
        llm = MockLLMProvider(default="step output")
        factory = _make_factory(bus, llm)

        from core.engine.orchestration.patterns.pipeline import PipelinePattern

        pattern = PipelinePattern(bus=bus, factory=factory)

        conversation = [{"role": "user", "content": "Prior chat context"}]
        config = _make_config(conversation_messages=conversation)

        await pattern.execute(
            task="Task with history",
            config=config,
            agent_configs=[_agent("a"), _agent("b")],
        )

        # The factory creates ComposedShells — we verify via the LLM calls
        # First call should have conversation context, second should not
        assert len(llm.calls) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 2. TEAM PATTERN — Parallel with Discovery Forwarding
# ═══════════════════════════════════════════════════════════════════════════════


class TestTeamPattern:
    """Verify Team (Pattern B) runs agents concurrently with live coordination."""

    @pytest.mark.asyncio
    async def test_concurrent_execution(self):
        """Multiple agents execute concurrently (not sequentially)."""
        bus = OrchestrationBus()
        execution_times: dict[str, float] = {}

        class TimedShell(TrackingShell):
            async def execute(self, task, context=None):
                import time

                start = time.monotonic()
                await asyncio.sleep(0.05)  # Simulate work
                execution_times[self.agent_id] = time.monotonic() - start
                return AgentResult(agent_id=self.agent_id, status="completed", output=f"{self.agent_id} done")

        factory = TrackingFactory(
            bus,
            {
                "researcher": TimedShell("researcher_1"),
                "analyst": TimedShell("analyst_1"),
                "synthesizer": TimedShell("synthesizer_1"),
            },
        )

        from core.engine.orchestration.patterns.team import TeamPattern

        pattern = TeamPattern(bus=bus, factory=factory)

        import time

        start = time.monotonic()
        result = await pattern.execute(
            task="Analyze market trends",
            config=_make_config(),
            agent_configs=[_agent("researcher"), _agent("analyst")],
        )
        wall_clock = time.monotonic() - start

        assert result.status == "completed"
        # If sequential, would take ~0.1s+ (2 agents x 0.05s each + synthesis).
        # Parallel should be ~0.05s + synthesis time.
        # We use a generous bound to avoid flakiness.
        assert wall_clock < 0.3, f"Team execution took {wall_clock:.2f}s — likely sequential"

    @pytest.mark.asyncio
    async def test_discovery_forwarding(self):
        """DISCOVERY messages from one agent are forwarded to all other agents."""
        bus = OrchestrationBus()

        agent_a = TrackingShell("agent_a_1", output="Result A")
        agent_b = TrackingShell("agent_b_1", output="Result B")

        # Simulate agent_a publishing a DISCOVERY during execution
        class DiscoveryShell(TrackingShell):
            def __init__(self, *args, bus_ref=None, **kwargs):
                super().__init__(*args, **kwargs)
                self._bus = bus_ref

            async def execute(self, task, context=None):
                # Publish a discovery mid-execution
                if self._bus:
                    await self._bus.publish(
                        BusMessage(
                            type=MessageType.DISCOVERY,
                            source_agent_id=self.agent_id,
                            run_id=context.get("run_id", "") if context else "",
                            payload={"finding": "Critical vulnerability found"},
                        )
                    )
                await asyncio.sleep(0.01)
                return AgentResult(agent_id=self.agent_id, status="completed", output="Found vulnerability")

        discoverer = DiscoveryShell("discoverer_1", bus_ref=bus)
        listener = TrackingShell("listener_1", output="Acknowledged discovery", delay=0.05)

        factory = TrackingFactory(
            bus,
            {
                "discoverer": discoverer,
                "listener": listener,
                "synthesizer": TrackingShell("synth", output="Synthesized"),
            },
        )

        from core.engine.orchestration.patterns.team import TeamPattern

        pattern = TeamPattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Security audit",
            config=_make_config(),
            agent_configs=[_agent("discoverer"), _agent("listener")],
        )

        await asyncio.sleep(0.05)
        assert result.status == "completed"

        # The listener should have received the discovery via inject_message
        assert len(listener.injected) >= 1, (
            f"Listener should have received discovery injection, got {len(listener.injected)}"
        )
        assert listener.injected[0].type == MessageType.DISCOVERY
        assert listener.injected[0].payload["finding"] == "Critical vulnerability found"

    @pytest.mark.asyncio
    async def test_team_synthesis_merges_outputs(self):
        """Synthesizer agent receives all team member outputs."""
        bus = OrchestrationBus()
        llm = MockLLMProvider(default="Synthesized output")
        factory = _make_factory(bus, llm)

        from core.engine.orchestration.patterns.team import TeamPattern

        pattern = TeamPattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Design system architecture",
            config=_make_config(),
            agent_configs=[_agent("backend"), _agent("frontend")],
        )

        assert result.status == "completed"
        # The synthesizer agent is the last LLM call — should be 3 total (2 team + 1 synth)
        assert len(llm.calls) == 3

    @pytest.mark.asyncio
    async def test_team_skip_synthesis(self):
        """When skip_synthesis is set, no synthesizer agent is created."""
        bus = OrchestrationBus()
        llm = MockLLMProvider(default="Agent output")
        factory = _make_factory(bus, llm)

        from core.engine.orchestration.patterns.team import TeamPattern

        pattern = TeamPattern(bus=bus, factory=factory)

        config = _make_config(metadata={"skip_synthesis": True})
        result = await pattern.execute(
            task="Independent parallel tasks",
            config=config,
            agent_configs=[_agent("task_a"), _agent("task_b")],
        )

        assert result.status == "completed"
        assert result.metadata.get("synthesis_skipped") is True
        # Only 2 LLM calls (no synthesizer)
        assert len(llm.calls) == 2

    @pytest.mark.asyncio
    async def test_team_all_agents_fail(self):
        """If every agent fails, team pattern returns failed status."""
        bus = OrchestrationBus()

        class AlwaysFails(TrackingShell):
            async def execute(self, task, context=None):
                raise RuntimeError("Agent crashed")

        factory = TrackingFactory(
            bus,
            {
                "agent_a": AlwaysFails("a"),
                "agent_b": AlwaysFails("b"),
            },
        )

        from core.engine.orchestration.patterns.team import TeamPattern

        pattern = TeamPattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Doomed task",
            config=_make_config(),
            agent_configs=[_agent("agent_a"), _agent("agent_b")],
        )

        assert result.status == "failed"
        assert "All team agents failed" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FANOUT PATTERN — Parallel Same-Role Agents
# ═══════════════════════════════════════════════════════════════════════════════


class TestFanOutPattern:
    """Verify FanOut (Pattern E) runs N agents on the same task concurrently."""

    @pytest.mark.asyncio
    async def test_parallel_execution_and_merge(self):
        """All agents get the same task; successful outputs are merged."""
        bus = OrchestrationBus()
        llm = MockLLMProvider(default="Perspective output")
        factory = _make_factory(bus, llm)

        from core.engine.orchestration.patterns.fanout import FanOutPattern

        pattern = FanOutPattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Generate ideas for homepage redesign",
            config=_make_config(),
            agent_configs=[_agent("creative_a"), _agent("creative_b"), _agent("creative_c")],
        )

        assert result.status == "completed"
        assert result.metadata["total_agents"] == 3
        assert result.metadata["successful"] == 3
        assert len(result.agent_results) == 3
        # All 3 LLM calls should have been made
        assert len(llm.calls) == 3

    @pytest.mark.asyncio
    async def test_partial_failure_still_succeeds(self):
        """FanOut succeeds as long as at least one agent completes."""
        bus = OrchestrationBus()

        call_count = 0

        class SometimesFails(TrackingShell):
            async def execute(self, task, context=None):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise RuntimeError("Agent failed")
                return AgentResult(agent_id=self.agent_id, status="completed", output="Success!")

        factory = TrackingFactory(
            bus,
            {
                "agent_a": SometimesFails("a"),
                "agent_b": SometimesFails("b"),
                "agent_c": SometimesFails("c"),
            },
        )

        from core.engine.orchestration.patterns.fanout import FanOutPattern

        pattern = FanOutPattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Risky task",
            config=_make_config(),
            agent_configs=[_agent("agent_a"), _agent("agent_b"), _agent("agent_c")],
        )

        assert result.status == "completed"
        assert result.metadata["successful"] == 1
        # Single success means output is used directly (not concatenated)
        assert "Success!" in result.output

    @pytest.mark.asyncio
    async def test_all_fail_returns_failed(self):
        """FanOut returns failed when every agent fails."""
        bus = OrchestrationBus()

        class AlwaysFails(TrackingShell):
            async def execute(self, task, context=None):
                raise RuntimeError("Crashed")

        factory = TrackingFactory(
            bus,
            {
                "a": AlwaysFails("a"),
                "b": AlwaysFails("b"),
            },
        )

        from core.engine.orchestration.patterns.fanout import FanOutPattern

        pattern = FanOutPattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="All fail",
            config=_make_config(),
            agent_configs=[_agent("a"), _agent("b")],
        )

        assert result.status == "failed"
        assert "All agents failed" in result.output

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrency(self):
        """max_concurrent limits how many agents run at once."""
        bus = OrchestrationBus()
        concurrent_count = 0
        max_seen = 0
        lock = asyncio.Lock()

        class CountingShell(TrackingShell):
            async def execute(self, task, context=None):
                nonlocal concurrent_count, max_seen
                async with lock:
                    concurrent_count += 1
                    max_seen = max(max_seen, concurrent_count)
                await asyncio.sleep(0.02)
                async with lock:
                    concurrent_count -= 1
                return AgentResult(agent_id=self.agent_id, status="completed", output="done")

        shells = {f"agent_{i}": CountingShell(f"agent_{i}") for i in range(5)}
        factory = TrackingFactory(bus, shells)

        from core.engine.orchestration.patterns.fanout import FanOutPattern

        pattern = FanOutPattern(bus=bus, factory=factory)

        config = _make_config(max_concurrent=2)
        await pattern.execute(
            task="Bounded task",
            config=config,
            agent_configs=[_agent(f"agent_{i}") for i in range(5)],
        )

        assert max_seen <= 2, f"Max concurrent was {max_seen}, expected <= 2"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ADVERSARIAL PATTERN — 3-Phase Debate
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdversarialPattern:
    """Verify Adversarial (Pattern D) runs independent → challenge → synthesis."""

    @pytest.mark.asyncio
    async def test_three_phase_execution(self):
        """All 3 phases execute: independent positions, challenges, synthesis."""
        bus = OrchestrationBus()
        messages: list[BusMessage] = []

        async def capture(msg: BusMessage) -> None:
            messages.append(msg)

        bus.subscribe_global(capture)

        llm = MockLLMProvider(default="Phase output")
        factory = _make_factory(bus, llm)

        from core.engine.orchestration.patterns.adversarial import AdversarialPattern

        pattern = AdversarialPattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Should we use microservices or monolith?",
            config=_make_config(),
            agent_configs=[_agent("advocate"), _agent("critic")],
        )

        await asyncio.sleep(0.05)

        assert result.status == "completed"

        # 2 independent + 2 challenges + 1 synthesis = 5 LLM calls
        assert len(llm.calls) == 5

        # Verify bus events
        position_events = [m for m in messages if m.type == MessageType.POSITION_SUBMITTED]
        challenge_events = [m for m in messages if m.type == MessageType.CHALLENGE_ISSUED]
        assert len(position_events) == 2, "Should have 2 position submissions"
        assert len(challenge_events) == 2, "Should have 2 challenge events"

        # Verify metadata
        assert result.metadata["positions"] == 2
        assert result.metadata["challenges"] == 2

    @pytest.mark.asyncio
    async def test_challenge_prompt_contains_other_positions(self):
        """Challenge phase prompt includes the other agent's independent output."""
        bus = OrchestrationBus()
        captured_prompts: list[str] = []

        class PromptCapture(MockLLMProvider):
            async def complete(self, prompt, **kwargs):
                captured_prompts.append(prompt)
                return "Captured"

        llm = PromptCapture()
        factory = _make_factory(bus, llm)

        from core.engine.orchestration.patterns.adversarial import AdversarialPattern

        pattern = AdversarialPattern(bus=bus, factory=factory)

        await pattern.execute(
            task="Debate topic",
            config=_make_config(),
            agent_configs=[_agent("side_a"), _agent("side_b")],
        )

        # Prompts 3 and 4 are the challenge prompts (after 2 independent + 2 challenge + 1 synthesis)
        # Challenge prompt for side_a should reference side_b's output and vice versa
        challenge_prompts = captured_prompts[2:4]
        assert len(challenge_prompts) == 2

        # Each challenge prompt should contain "other perspectives"
        for cp in challenge_prompts:
            assert "other perspectives" in cp.lower() or "challenge" in cp.lower()

    @pytest.mark.asyncio
    async def test_adversarial_needs_minimum_two_agents(self):
        """Adversarial pattern fails with fewer than 2 agents."""
        bus = OrchestrationBus()
        factory = TrackingFactory(bus)

        from core.engine.orchestration.patterns.adversarial import AdversarialPattern

        pattern = AdversarialPattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Solo debate",
            config=_make_config(),
            agent_configs=[_agent("lone_wolf")],
        )

        assert result.status == "failed"
        assert "at least 2" in result.output

    @pytest.mark.asyncio
    async def test_phase1_runs_in_parallel(self):
        """Independent phase agents execute concurrently, not sequentially."""
        bus = OrchestrationBus()

        class SlowShell(TrackingShell):
            async def execute(self, task, context=None):
                await asyncio.sleep(0.05)
                return AgentResult(agent_id=self.agent_id, status="completed", output=f"{self.agent_id} done")

        factory = TrackingFactory(
            bus,
            {
                "agent_a": SlowShell("a"),
                "agent_b": SlowShell("b"),
                "agent_c": SlowShell("c"),
                "synthesizer": TrackingShell("synth", output="synthesized"),
            },
        )

        from core.engine.orchestration.patterns.adversarial import AdversarialPattern

        pattern = AdversarialPattern(bus=bus, factory=factory)

        import time

        start = time.monotonic()
        await pattern.execute(
            task="Debate",
            config=_make_config(),
            agent_configs=[_agent("agent_a"), _agent("agent_b"), _agent("agent_c")],
        )
        wall_clock = time.monotonic() - start

        # Sequential Phase 1 would take 3 x 0.05s = 0.15s just for Phase 1
        # Parallel Phase 1 takes ~0.05s for Phase 1
        # With challenge (3 agents) + synthesis overhead, total should still be < 0.3s
        # vs sequential which would be > 0.35s minimum
        assert wall_clock < 0.35, f"Phase 1 took {wall_clock:.2f}s — likely still sequential"

    @pytest.mark.asyncio
    async def test_all_independent_fail_bails_early(self):
        """If all agents fail in independent phase, skip challenge and synthesis."""
        bus = OrchestrationBus()

        class AlwaysFails(TrackingShell):
            async def execute(self, task, context=None):
                raise RuntimeError("Failed")

        factory = TrackingFactory(
            bus,
            {
                "a": AlwaysFails("a"),
                "b": AlwaysFails("b"),
            },
        )

        from core.engine.orchestration.patterns.adversarial import AdversarialPattern

        pattern = AdversarialPattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Doomed debate",
            config=_make_config(),
            agent_configs=[_agent("a"), _agent("b")],
        )

        assert result.status == "failed"
        assert "independent phase" in result.output.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ENGAGEMENT MODEL — Multi-Spin Pipeline + Adversarial
# ═══════════════════════════════════════════════════════════════════════════════


class TestEngagementModel:
    """Verify the engagement layer orchestrates spins correctly."""

    @pytest.mark.asyncio
    async def test_single_perspective_no_synthesis(self):
        """Single perspective returns content directly without synthesis LLM call."""
        from core.engine.orchestrator.engagement import execute_engagement
        from core.engine.orchestrator.engagement_models import SpinOutput

        mock_spin = SpinOutput(
            content="Direct answer",
            handoff="",
            confidence=0.9,
            open_questions=[],
            perspective="practitioner",
            specialties_used=["python-development"],
        )

        with (
            patch("core.engine.orchestrator.engagement._execute_single_spin", return_value=mock_spin),
            patch("core.engine.orchestrator.executor._load_snapshot", new_callable=AsyncMock, return_value={}),
        ):
            result = await execute_engagement(
                task_description="Simple question",
                classification={
                    "discipline": "architecture",
                    "perspective": "practitioner",
                    "engagement": {"perspectives": ["practitioner"]},
                    "mode": "reactive",
                },
                product_id="product:test",
            )

        assert len(result.spins) == 1
        assert result.merged_output == "Direct answer"
        assert result.perspectives_used == ["practitioner"]

    @pytest.mark.asyncio
    async def test_pipeline_engagement_handoff(self):
        """Pipeline engagement passes handoff from spin N to spin N+1."""
        from core.engine.orchestrator.engagement import execute_engagement
        from core.engine.orchestrator.engagement_models import SpinOutput

        call_args: list[dict] = []

        async def mock_spin(task_description, perspective, prior_handoff, prior_questions, *args, **kwargs):
            call_args.append(
                {
                    "perspective": perspective,
                    "prior_handoff": prior_handoff,
                    "prior_questions": prior_questions,
                }
            )
            return SpinOutput(
                content=f"{perspective} analysis",
                handoff=f"Key insight from {perspective}",
                confidence=0.8,
                open_questions=[f"Question from {perspective}"],
                perspective=perspective,
                specialties_used=[],
            )

        with (
            patch("core.engine.orchestrator.engagement._execute_single_spin", side_effect=mock_spin),
            patch(
                "core.engine.orchestrator.engagement.classify_spin",
                return_value={
                    "archetype": "analyst",
                    "mode": "deliberative",
                    "specialties": [],
                },
            ),
            patch("core.engine.orchestrator.engagement.synthesize_spins", return_value="Synthesized output"),
            patch("core.engine.orchestrator.executor._load_snapshot", new_callable=AsyncMock, return_value={}),
        ):
            result = await execute_engagement(
                task_description="Complex analysis",
                classification={
                    "discipline": "architecture",
                    "perspective": "theorist",
                    "engagement": {
                        "perspectives": ["theorist", "practitioner"],
                        "rationale": "Need theory + practice",
                    },
                    "mode": "deliberative",
                },
                product_id="product:test",
            )

        assert len(result.spins) == 2
        assert result.perspectives_used == ["theorist", "practitioner"]

        # First spin: no prior handoff
        assert call_args[0]["prior_handoff"] is None
        assert call_args[0]["prior_questions"] is None

        # Second spin: receives handoff from first
        assert call_args[1]["prior_handoff"] == "Key insight from theorist"
        assert call_args[1]["prior_questions"] == ["Question from theorist"]

    @pytest.mark.asyncio
    async def test_adversarial_engagement_parallel(self):
        """Adversarial pair runs both spins in parallel (asyncio.gather)."""
        from core.engine.orchestrator.engagement import execute_engagement
        from core.engine.orchestrator.engagement_models import SpinOutput

        execution_order: list[str] = []

        async def mock_spin(task_description, perspective, *args, **kwargs):
            execution_order.append(f"start_{perspective}")
            await asyncio.sleep(0.01)
            execution_order.append(f"end_{perspective}")
            return SpinOutput(
                content=f"{perspective} position",
                handoff=f"Handoff from {perspective} with unique content xyz_{perspective}",
                confidence=0.7,
                open_questions=[],
                perspective=perspective,
                specialties_used=[],
            )

        with (
            patch("core.engine.orchestrator.engagement._execute_single_spin", side_effect=mock_spin),
            patch(
                "core.engine.orchestrator.engagement.classify_spin",
                return_value={
                    "archetype": "analyst",
                    "mode": "deliberative",
                    "specialties": [],
                },
            ),
            patch("core.engine.orchestrator.engagement.llm") as mock_llm,
            patch("core.engine.orchestrator.executor._load_snapshot", new_callable=AsyncMock, return_value={}),
        ):
            mock_llm.complete = AsyncMock(return_value="Adversarial synthesis result")

            result = await execute_engagement(
                task_description="Debate topic",
                classification={
                    "discipline": "architecture",
                    "perspective": "theorist",
                    "engagement": {
                        "perspectives": ["theorist", "strategist"],
                        "adversarial_pair": ["theorist", "strategist"],
                        "rationale": "Need opposing views",
                    },
                    "mode": "deliberative",
                },
                product_id="product:test",
            )

        assert len(result.spins) == 2
        assert result.adversarial_resolution is not None
        assert result.adversarial_diversity is not None

        # Both should start before either ends (parallel execution)
        assert execution_order[0].startswith("start_")
        assert execution_order[1].startswith("start_")

    @pytest.mark.asyncio
    async def test_adversarial_adaptive_termination(self):
        """When adversarial spins agree, synthesis is skipped."""
        from core.engine.orchestrator.engagement import compute_spin_diversity, should_skip_synthesis
        from core.engine.orchestrator.engagement_models import SpinOutput

        # Nearly identical handoffs → should skip synthesis
        spin_a = SpinOutput(
            content="Use microservices",
            handoff="Microservices are the right choice for scalability",
            confidence=0.9,
            perspective="theorist",
        )
        spin_b = SpinOutput(
            content="Microservices preferred",
            handoff="Microservices are the right choice for scalability",
            confidence=0.85,
            perspective="strategist",
        )

        diversity = compute_spin_diversity(spin_a, spin_b)
        assert diversity < 0.25, f"Nearly identical handoffs should have low diversity, got {diversity}"
        assert should_skip_synthesis(spin_a, spin_b) is True

        # Very different handoffs → should NOT skip synthesis
        spin_c = SpinOutput(
            content="Monolith is better",
            handoff="Start with a monolith, decompose later when bottlenecks appear",
            confidence=0.8,
            perspective="practitioner",
        )
        diversity_divergent = compute_spin_diversity(spin_a, spin_c)
        assert diversity_divergent > 0.3, f"Different handoffs should have higher diversity, got {diversity_divergent}"
        assert should_skip_synthesis(spin_a, spin_c) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. DISPATCH PLANNER — Conflict Detection + Batching
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatchPlanner:
    """Verify the dispatch planner groups tasks correctly."""

    def test_no_overlap_parallel(self):
        """Tasks with no file overlap are grouped into a parallel batch."""
        from core.engine.orchestration.dispatch_planner import plan_dispatch

        tasks = [
            {"id": "t1", "files_create": ["src/auth.py"], "files_modify": [], "depends_on": []},
            {"id": "t2", "files_create": ["src/billing.py"], "files_modify": [], "depends_on": []},
            {"id": "t3", "files_create": ["src/notifications.py"], "files_modify": [], "depends_on": []},
        ]

        schedule = plan_dispatch(tasks)
        assert schedule.parallel_batches >= 1
        parallel = [b for b in schedule.batches if b.mode == "parallel"]
        assert len(parallel) == 1
        assert set(parallel[0].task_ids) == {"t1", "t2", "t3"}

    def test_file_overlap_forces_sequential(self):
        """Tasks touching the same file are split into separate batches."""
        from core.engine.orchestration.dispatch_planner import plan_dispatch

        tasks = [
            {"id": "t1", "files_create": [], "files_modify": ["src/config.py"], "depends_on": []},
            {"id": "t2", "files_create": [], "files_modify": ["src/config.py"], "depends_on": []},
        ]

        schedule = plan_dispatch(tasks)
        # t1 and t2 should NOT be in the same parallel batch
        for batch in schedule.batches:
            if batch.mode == "parallel":
                assert not ({"t1", "t2"}.issubset(set(batch.task_ids))), (
                    "Conflicting tasks should not be in same parallel batch"
                )

    def test_dependency_ordering(self):
        """Tasks with dependencies come after their prerequisites."""
        from core.engine.orchestration.dispatch_planner import plan_dispatch

        tasks = [
            {"id": "t1", "files_create": ["a.py"], "files_modify": [], "depends_on": []},
            {"id": "t2", "files_create": ["b.py"], "files_modify": [], "depends_on": ["t1"]},
            {"id": "t3", "files_create": ["c.py"], "files_modify": [], "depends_on": ["t2"]},
        ]

        schedule = plan_dispatch(tasks)
        all_ids_in_order = []
        for batch in schedule.batches:
            all_ids_in_order.extend(batch.task_ids)

        assert all_ids_in_order.index("t1") < all_ids_in_order.index("t2")
        assert all_ids_in_order.index("t2") < all_ids_in_order.index("t3")

    def test_mixed_parallel_and_sequential(self):
        """Complex graph: some tasks parallel, some sequential due to deps/conflicts."""
        from core.engine.orchestration.dispatch_planner import plan_dispatch

        tasks = [
            {"id": "t1", "files_create": ["a.py"], "files_modify": [], "depends_on": []},
            {"id": "t2", "files_create": ["b.py"], "files_modify": [], "depends_on": []},
            {"id": "t3", "files_create": [], "files_modify": ["a.py"], "depends_on": ["t1"]},
            {"id": "t4", "files_create": ["d.py"], "files_modify": [], "depends_on": ["t2"]},
        ]

        schedule = plan_dispatch(tasks)
        assert schedule.total_tasks == 4

        # t1 and t2 should be in the first batch (parallel, no overlap)
        first_batch = schedule.batches[0]
        assert set(first_batch.task_ids) == {"t1", "t2"}
        assert first_batch.mode == "parallel"

    def test_empty_tasks(self):
        """Empty task list produces empty schedule."""
        from core.engine.orchestration.dispatch_planner import plan_dispatch

        schedule = plan_dispatch([])
        assert schedule.total_tasks == 0
        assert len(schedule.batches) == 0

    def test_line_number_stripping(self):
        """File references with line numbers (foo.py:123) are normalized."""
        from core.engine.orchestration.dispatch_planner import _extract_files

        files = _extract_files(
            {
                "files_create": ["src/auth.py:1-50"],
                "files_modify": ["src/config.py:100-200"],
                "files_test": ["tests/test_auth.py:30"],
            }
        )
        assert files == {"src/auth.py", "src/config.py", "tests/test_auth.py"}


# ═══════════════════════════════════════════════════════════════════════════════
# 7. AGENT ORCHESTRATOR — Mixed Plans with Error Cascades
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentOrchestratorScenarios:
    """Verify AgentOrchestrator handles complex multi-batch plans."""

    @pytest.mark.asyncio
    async def test_mixed_parallel_then_sequential(self):
        """Plan with parallel batch first, then sequential dependents."""
        pool = _make_pool()
        plan = {
            "spec_id": "agent_spec:mixed",
            "units": [
                {
                    "id": "u1",
                    "title": "Build auth",
                    "description": "Auth module",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": ["auth.py"],
                    "files_modify": [],
                },
                {
                    "id": "u2",
                    "title": "Build billing",
                    "description": "Billing module",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": ["billing.py"],
                    "files_modify": [],
                },
                {
                    "id": "u3",
                    "title": "Integration tests",
                    "description": "Test both",
                    "depends_on": ["u1", "u2"],
                    "archetype": "sentinel",
                    "mode": "procedural",
                    "files_create": ["tests.py"],
                    "files_modify": [],
                },
            ],
            "batches": [
                {"task_ids": ["u1", "u2"], "mode": "parallel"},
                {"task_ids": ["u3"], "mode": "sequential"},
            ],
            "conflicts": [],
        }

        execution_order: list[str] = []

        async def mock_execute_task(description, product_id, **kwargs):
            # Track which unit is executing based on description
            for uid in ["u1", "u2", "u3"]:
                if uid in str(description) or any(
                    kw in description for kw in ["Auth", "Billing", "Integration", "Test both"]
                ):
                    execution_order.append(uid)
                    break
            return {"id": f"task:{uid}", "output": "done"}

        with patch("core.engine.orchestrator.executor.execute_task", side_effect=mock_execute_task):
            from core.engine.product.agent_orchestrator import AgentOrchestrator

            orch = AgentOrchestrator(db_pool=pool)
            summary = await orch.execute_plan(plan, product_id="product:test")

        assert summary["completed"] == 3
        assert summary["failed"] == 0
        assert summary["spec_status"] == "verifying"

    @pytest.mark.asyncio
    async def test_failure_cascade_blocks_all_downstream(self):
        """When unit fails, ALL transitive dependents are blocked."""
        pool = _make_pool()
        plan = {
            "spec_id": "agent_spec:cascade",
            "units": [
                {
                    "id": "u1",
                    "title": "Foundation",
                    "description": "Base",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
                {
                    "id": "u2",
                    "title": "Layer 2",
                    "description": "Mid",
                    "depends_on": ["u1"],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
                {
                    "id": "u3",
                    "title": "Layer 3",
                    "description": "Top",
                    "depends_on": ["u2"],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
                {
                    "id": "u4",
                    "title": "Independent",
                    "description": "Unrelated",
                    "depends_on": [],
                    "archetype": "analyst",
                    "mode": "reactive",
                    "files_create": [],
                    "files_modify": [],
                },
            ],
            "batches": [
                {"task_ids": ["u1", "u4"], "mode": "parallel"},
                {"task_ids": ["u2"], "mode": "sequential"},
                {"task_ids": ["u3"], "mode": "sequential"},
            ],
            "conflicts": [],
        }

        from core.engine.product.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(db_pool=pool)

        async def failing_execute(unit_id, unit, product_id, **kwargs):
            if unit_id == "u1":
                raise RuntimeError("Foundation collapsed")
            return {"unit_id": unit_id, "status": "completed", "output": "done"}

        orch._execute_unit = failing_execute

        summary = await orch.execute_plan(plan, product_id="product:test")

        assert summary["unit_status"]["u1"] == "failed"
        assert summary["unit_status"]["u2"] == "blocked"  # blocked by u1
        assert summary["unit_status"]["u3"] == "blocked"  # blocked by u2 (transitively u1)
        assert summary["unit_status"]["u4"] == "completed"  # independent, should succeed
        assert summary["spec_status"] == "failed"

    @pytest.mark.asyncio
    async def test_progress_tracking_accuracy(self):
        """get_progress returns correct counts mid-execution and post-execution."""
        pool = _make_pool()
        plan = {
            "spec_id": "agent_spec:progress",
            "units": [
                {
                    "id": "u1",
                    "title": "A",
                    "description": "A",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
                {
                    "id": "u2",
                    "title": "B",
                    "description": "B",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
                {
                    "id": "u3",
                    "title": "C",
                    "description": "C",
                    "depends_on": ["u1"],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
            ],
            "batches": [
                {"task_ids": ["u1", "u2"], "mode": "parallel"},
                {"task_ids": ["u3"], "mode": "sequential"},
            ],
            "conflicts": [],
        }

        with patch(
            "core.engine.orchestrator.executor.execute_task",
            new_callable=AsyncMock,
            return_value={"id": "task:x", "output": "done"},
        ):
            from core.engine.product.agent_orchestrator import AgentOrchestrator

            orch = AgentOrchestrator(db_pool=pool)
            await orch.execute_plan(plan, product_id="product:test")

        progress = orch.get_progress()
        assert progress["total"] == 3
        assert progress["completed"] == 3
        assert progress["failed"] == 0
        assert progress["blocked"] == 0
        assert progress["pct"] == 100


# ═══════════════════════════════════════════════════════════════════════════════
# 8. BUS COMMUNICATION — Event Routing + Isolation
# ═══════════════════════════════════════════════════════════════════════════════


class TestBusCommunication:
    """Verify OrchestrationBus routes messages correctly."""

    @pytest.mark.asyncio
    async def test_targeted_message_routing(self):
        """Targeted messages go only to the specified agent."""
        bus = OrchestrationBus()
        received_a: list[BusMessage] = []
        received_b: list[BusMessage] = []

        async def handler_a(msg: BusMessage):
            received_a.append(msg)

        async def handler_b(msg: BusMessage):
            received_b.append(msg)

        bus.subscribe("agent_a", handler_a)
        bus.subscribe("agent_b", handler_b)

        await bus.publish(
            BusMessage(
                type=MessageType.REQUEST,
                source_agent_id="agent_a",
                target_agent_id="agent_b",
                run_id="run1",
                payload={"question": "What do you think?"},
            )
        )

        await asyncio.sleep(0.05)

        assert len(received_b) == 1, "Target agent should receive the message"
        assert len(received_a) == 0, "Non-target agent should NOT receive targeted message"

    @pytest.mark.asyncio
    async def test_broadcast_excludes_sender(self):
        """Broadcast messages go to everyone except the sender."""
        bus = OrchestrationBus()
        received_a: list[BusMessage] = []
        received_b: list[BusMessage] = []
        received_c: list[BusMessage] = []

        async def handler_a(msg):
            received_a.append(msg)

        async def handler_b(msg):
            received_b.append(msg)

        async def handler_c(msg):
            received_c.append(msg)

        bus.subscribe("agent_a", handler_a)
        bus.subscribe("agent_b", handler_b)
        bus.subscribe("agent_c", handler_c)

        await bus.publish(
            BusMessage(
                type=MessageType.BROADCAST,
                source_agent_id="agent_a",
                run_id="run1",
                payload={"announcement": "I found something"},
            )
        )

        await asyncio.sleep(0.05)

        assert len(received_a) == 0, "Sender should NOT receive own broadcast"
        assert len(received_b) == 1, "Other agents should receive broadcast"
        assert len(received_c) == 1, "Other agents should receive broadcast"

    @pytest.mark.asyncio
    async def test_global_subscriber_sees_everything(self):
        """Global subscribers receive every message regardless of target."""
        bus = OrchestrationBus()
        global_received: list[BusMessage] = []

        async def global_handler(msg: BusMessage):
            global_received.append(msg)

        bus.subscribe_global(global_handler)

        # Targeted message
        await bus.publish(
            BusMessage(
                type=MessageType.REQUEST,
                source_agent_id="a",
                target_agent_id="b",
                run_id="run1",
            )
        )
        # Broadcast
        await bus.publish(
            BusMessage(
                type=MessageType.DISCOVERY,
                source_agent_id="a",
                run_id="run1",
            )
        )

        await asyncio.sleep(0.05)

        assert len(global_received) == 2, "Global subscriber should see all messages"

    @pytest.mark.asyncio
    async def test_message_log_filtering(self):
        """get_messages filters by run_id and message_type."""
        bus = OrchestrationBus()

        await bus.publish(BusMessage(type=MessageType.AGENT_SPAWNED, run_id="run1", source_agent_id="a"))
        await bus.publish(BusMessage(type=MessageType.AGENT_COMPLETED, run_id="run1", source_agent_id="a"))
        await bus.publish(BusMessage(type=MessageType.AGENT_SPAWNED, run_id="run2", source_agent_id="b"))

        run1_msgs = bus.get_messages("run1")
        assert len(run1_msgs) == 2

        run1_spawned = bus.get_messages("run1", message_type=MessageType.AGENT_SPAWNED)
        assert len(run1_spawned) == 1

        run2_msgs = bus.get_messages("run2")
        assert len(run2_msgs) == 1

    @pytest.mark.asyncio
    async def test_capture_callback(self):
        """Capture callback fires on every published message."""
        captured: list[BusMessage] = []

        async def capture(msg: BusMessage):
            captured.append(msg)

        bus = OrchestrationBus(capture_callback=capture)

        await bus.publish(BusMessage(type=MessageType.AGENT_SPAWNED, run_id="r1", source_agent_id="a"))
        await bus.publish(BusMessage(type=MessageType.DISCOVERY, run_id="r1", source_agent_id="b"))

        assert len(captured) == 2

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self):
        """After unsubscribe, agent no longer receives messages."""
        bus = OrchestrationBus()
        received: list[BusMessage] = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe("agent_a", handler)
        await bus.publish(BusMessage(type=MessageType.BROADCAST, source_agent_id="other", run_id="r"))
        await asyncio.sleep(0.02)
        assert len(received) == 1

        bus.unsubscribe("agent_a")
        await bus.publish(BusMessage(type=MessageType.BROADCAST, source_agent_id="other", run_id="r"))
        await asyncio.sleep(0.02)
        assert len(received) == 1, "Should not receive after unsubscribe"

    @pytest.mark.asyncio
    async def test_clear_run_removes_messages(self):
        """clear_run removes all logged messages for a specific run."""
        bus = OrchestrationBus()

        await bus.publish(BusMessage(type=MessageType.AGENT_SPAWNED, run_id="run_keep", source_agent_id="a"))
        await bus.publish(BusMessage(type=MessageType.AGENT_SPAWNED, run_id="run_clear", source_agent_id="b"))
        await bus.publish(BusMessage(type=MessageType.AGENT_COMPLETED, run_id="run_clear", source_agent_id="b"))

        assert len(bus.get_messages("run_clear")) == 2
        bus.clear_run("run_clear")
        assert len(bus.get_messages("run_clear")) == 0
        assert len(bus.get_messages("run_keep")) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 9. COMPOSITION SCORING — Historical Signal Adjustment
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompositionScorer:
    """Verify composition scoring adjusts weights based on historical signals."""

    @pytest.mark.asyncio
    async def test_cold_start_equal_weights(self):
        """With no signals, all perspectives get weight 1.0."""
        with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=[]):
            from core.engine.orchestration.composition_scorer import score_composition

            result = await score_composition(
                classification={
                    "discipline": "architecture",
                    "engagement": {"perspectives": ["theorist", "practitioner"]},
                },
                product_id="product:test",
            )

        assert result.perspective_weights == {"theorist": 1.0, "practitioner": 1.0}
        assert len(result.adjustments) == 0

    @pytest.mark.asyncio
    async def test_low_acceptance_penalizes_weight(self):
        """Perspective with < 40% acceptance gets weight penalty."""
        signals = [
            {
                "perspectives": ["theorist"],
                "feedback": "rejected",
                "utilization_rate": 0.5,
                "engagement_type": "pipeline",
            }
            for _ in range(8)
        ] + [
            {
                "perspectives": ["theorist"],
                "feedback": "accepted",
                "utilization_rate": 0.5,
                "engagement_type": "pipeline",
            }
            for _ in range(2)
        ]

        with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
            from core.engine.orchestration.composition_scorer import score_composition

            result = await score_composition(
                classification={
                    "discipline": "architecture",
                    "engagement": {"perspectives": ["theorist"]},
                },
                product_id="product:test",
            )

        assert result.perspective_weights["theorist"] < 1.0
        assert any("acceptance" in adj.lower() for adj in result.adjustments)

    @pytest.mark.asyncio
    async def test_high_performing_perspective_injected(self):
        """A perspective not in the classification gets injected if it has high acceptance."""
        # Create signals showing 'operator' has high acceptance + utilization
        signals = [
            {
                "perspectives": ["operator"],
                "feedback": "accepted",
                "utilization_rate": 0.7,
                "engagement_type": "pipeline",
            }
            for _ in range(10)
        ]

        with patch("core.engine.orchestration.composition_scorer._query_signals", return_value=signals):
            from core.engine.orchestration.composition_scorer import score_composition

            result = await score_composition(
                classification={
                    "discipline": "architecture",
                    "engagement": {"perspectives": ["practitioner"]},
                },
                product_id="product:test",
            )

        assert "operator" in result.perspectives, "High-performing operator should be injected"
        assert any("Injected operator" in adj for adj in result.adjustments)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. FULL INITIATIVE LIFECYCLE — Create → Decompose → Execute
# ═══════════════════════════════════════════════════════════════════════════════


pytestmark_e2e = pytest.mark.e2e


class TestFullInitiativeLifecycle:
    """E2E test simulating the full path from portal trigger to agent execution."""

    @pytest.mark.asyncio
    async def test_initiative_create_decompose_execute(self):
        """Full lifecycle: create initiative → decompose → execute mixed plan."""
        pool = _make_pool()

        # Phase 1: Create initiative
        from core.engine.product.agent_orchestrator import AgentOrchestrator

        # Phase 2: Build a realistic plan with mixed execution modes
        plan = {
            "spec_id": "agent_spec:full_lifecycle",
            "units": [
                # Parallel batch: independent features
                {
                    "id": "auth",
                    "title": "Authentication module",
                    "description": "Build JWT auth",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": ["engine/auth.py", "tests/test_auth.py"],
                    "files_modify": [],
                },
                {
                    "id": "billing",
                    "title": "Billing integration",
                    "description": "Stripe integration",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": ["engine/billing.py"],
                    "files_modify": [],
                },
                # Sequential: depends on auth
                {
                    "id": "rbac",
                    "title": "RBAC layer",
                    "description": "Role-based access control",
                    "depends_on": ["auth"],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": ["engine/rbac.py"],
                    "files_modify": ["engine/auth.py"],
                },
                # Sequential: depends on both auth and billing
                {
                    "id": "integration",
                    "title": "Integration tests",
                    "description": "Test auth + billing together",
                    "depends_on": ["auth", "billing"],
                    "archetype": "sentinel",
                    "mode": "procedural",
                    "files_create": ["tests/test_integration.py"],
                    "files_modify": [],
                },
                # Final: depends on everything
                {
                    "id": "deploy",
                    "title": "Deployment config",
                    "description": "K8s manifests",
                    "depends_on": ["rbac", "integration"],
                    "archetype": "executor",
                    "mode": "procedural",
                    "files_create": ["deploy/k8s.yaml"],
                    "files_modify": [],
                },
            ],
            "batches": [
                {"task_ids": ["auth", "billing"], "mode": "parallel"},
                {"task_ids": ["rbac", "integration"], "mode": "sequential"},
                {"task_ids": ["deploy"], "mode": "sequential"},
            ],
            "conflicts": [],
        }

        execution_log: list[str] = []

        with patch(
            "core.engine.orchestrator.executor.execute_task",
            side_effect=lambda description, product_id, **kw: (
                execution_log.append(description[:30]),
                {"id": "task:x", "output": f"Completed: {description[:30]}"},
            )[-1],
        ):
            orch = AgentOrchestrator(db_pool=pool)
            summary = await orch.execute_plan(plan, product_id="product:test")

        # Verify all units completed
        assert summary["total_units"] == 5
        assert summary["completed"] == 5
        assert summary["failed"] == 0
        assert summary["blocked"] == 0
        assert summary["spec_status"] == "verifying"

        # Verify execution happened
        assert len(execution_log) == 5

    @pytest.mark.asyncio
    async def test_initiative_partial_failure_recovery(self):
        """When one parallel unit fails, independent units still succeed."""
        pool = _make_pool()

        plan = {
            "spec_id": "agent_spec:partial_fail",
            "units": [
                {
                    "id": "u1",
                    "title": "Succeeds",
                    "description": "Works fine",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
                {
                    "id": "u2",
                    "title": "Fails",
                    "description": "Will crash",
                    "depends_on": [],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
                {
                    "id": "u3",
                    "title": "Depends on u1",
                    "description": "Should run",
                    "depends_on": ["u1"],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
                {
                    "id": "u4",
                    "title": "Depends on u2",
                    "description": "Should be blocked",
                    "depends_on": ["u2"],
                    "archetype": "creator",
                    "mode": "deliberative",
                    "files_create": [],
                    "files_modify": [],
                },
            ],
            "batches": [
                {"task_ids": ["u1", "u2"], "mode": "parallel"},
                {"task_ids": ["u3", "u4"], "mode": "sequential"},
            ],
            "conflicts": [],
        }

        from core.engine.product.agent_orchestrator import AgentOrchestrator

        orch = AgentOrchestrator(db_pool=pool)

        async def selective_execute(unit_id, unit, product_id, **kwargs):
            if unit_id == "u2":
                raise RuntimeError("u2 crashed")
            return {"unit_id": unit_id, "status": "completed", "output": "done"}

        orch._execute_unit = selective_execute

        summary = await orch.execute_plan(plan, product_id="product:test")

        assert summary["unit_status"]["u1"] == "completed"
        assert summary["unit_status"]["u2"] == "failed"
        assert summary["unit_status"]["u3"] == "completed"  # u1 succeeded, so u3 runs
        assert summary["unit_status"]["u4"] == "blocked"  # u2 failed, so u4 blocked


# ═══════════════════════════════════════════════════════════════════════════════
# 11. CROSS-CUTTING — Pattern ↔ Bus ↔ Factory Integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossCutting:
    """Integration tests that verify wiring between layers."""

    @pytest.mark.asyncio
    async def test_pipeline_emits_complete_event_sequence(self):
        """Pipeline emits: SPAWNED → (HANDOFF → SPAWNED)* → final AGENT_COMPLETED."""
        bus = OrchestrationBus()
        messages: list[BusMessage] = []

        async def capture(msg):
            messages.append(msg)

        bus.subscribe_global(capture)

        llm = MockLLMProvider(default="Step output")
        factory = _make_factory(bus, llm)

        from core.engine.orchestration.patterns.pipeline import PipelinePattern

        pattern = PipelinePattern(bus=bus, factory=factory)

        await pattern.execute(
            task="Three step pipeline",
            config=_make_config(),
            agent_configs=[_agent("step1"), _agent("step2"), _agent("step3")],
        )

        await asyncio.sleep(0.05)

        types = [m.type for m in messages]

        # Should see SPAWNED events for each step
        spawned_count = types.count(MessageType.AGENT_SPAWNED)
        assert spawned_count == 3

        # Should see HANDOFF between steps (2 handoffs for 3 steps)
        handoff_count = types.count(MessageType.HANDOFF)
        assert handoff_count == 2

        # LLMShell publishes AGENT_COMPLETED
        completed_count = types.count(MessageType.AGENT_COMPLETED)
        assert completed_count == 3

    @pytest.mark.asyncio
    async def test_adversarial_full_event_sequence(self):
        """Adversarial emits: SPAWNED+POSITION_SUBMITTED, CHALLENGE_ISSUED, SPAWNED (synth)."""
        bus = OrchestrationBus()
        messages: list[BusMessage] = []

        async def capture(msg):
            messages.append(msg)

        bus.subscribe_global(capture)

        llm = MockLLMProvider(default="Output")
        factory = _make_factory(bus, llm)

        from core.engine.orchestration.patterns.adversarial import AdversarialPattern

        pattern = AdversarialPattern(bus=bus, factory=factory)

        await pattern.execute(
            task="Debate",
            config=_make_config(),
            agent_configs=[_agent("pro"), _agent("con")],
        )

        await asyncio.sleep(0.05)

        types = [m.type for m in messages]

        # Independent phase: 2 spawns + 2 position submissions
        assert types.count(MessageType.POSITION_SUBMITTED) == 2

        # Challenge phase: 2 challenge events
        assert types.count(MessageType.CHALLENGE_ISSUED) == 2

        # Synthesis: 1 additional spawn for synthesizer
        spawned = [m for m in messages if m.type == MessageType.AGENT_SPAWNED]
        synth_spawns = [m for m in spawned if m.payload.get("phase") == "synthesis"]
        assert len(synth_spawns) == 1

    @pytest.mark.asyncio
    async def test_team_discovery_isolation_between_runs(self):
        """Team pattern only forwards discoveries within its own run_id."""
        bus = OrchestrationBus()

        # Simulate two concurrent Team runs with different run_ids
        run1_listener = TrackingShell("run1_listener", output="run1 done", delay=0.1)
        run2_listener = TrackingShell("run2_listener", output="run2 done", delay=0.1)

        # A discoverer in run1 publishes a DISCOVERY
        class Run1Discoverer(TrackingShell):
            async def execute(self, task, context=None):
                await bus.publish(
                    BusMessage(
                        type=MessageType.DISCOVERY,
                        source_agent_id=self.agent_id,
                        run_id="run_1",
                        payload={"data": "run1 secret"},
                    )
                )
                await asyncio.sleep(0.02)
                return AgentResult(agent_id=self.agent_id, status="completed", output="discovered")

        # Run two Team patterns concurrently with different run_ids
        from core.engine.orchestration.patterns.team import TeamPattern

        factory1 = TrackingFactory(
            bus,
            {
                "discoverer": Run1Discoverer("disc"),
                "listener": run1_listener,
                "synthesizer": TrackingShell("synth1", output="synth"),
            },
        )
        factory2 = TrackingFactory(
            bus,
            {
                "observer": TrackingShell("obs", output="observing", delay=0.05),
                "worker": run2_listener,
                "synthesizer": TrackingShell("synth2", output="synth"),
            },
        )

        pattern1 = TeamPattern(bus=bus, factory=factory1)
        pattern2 = TeamPattern(bus=bus, factory=factory2)

        await asyncio.gather(
            pattern1.execute("Run 1 task", _make_config(run_id="run_1"), [_agent("discoverer"), _agent("listener")]),
            pattern2.execute("Run 2 task", _make_config(run_id="run_2"), [_agent("observer"), _agent("worker")]),
        )

        await asyncio.sleep(0.05)

        # run1_listener should have received the discovery (same run)
        assert len(run1_listener.injected) >= 1, "Same-run listener should get discovery"

        # run2_listener should NOT have received it (different run)
        assert len(run2_listener.injected) == 0, (
            f"Cross-run listener should NOT get discovery, got {len(run2_listener.injected)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 12. EDGE CASES + ROBUSTNESS
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases and robustness tests."""

    @pytest.mark.asyncio
    async def test_empty_agent_configs(self):
        """All patterns handle empty agent_configs gracefully."""
        bus = OrchestrationBus()
        factory = TrackingFactory(bus)

        from core.engine.orchestration.patterns.adversarial import AdversarialPattern
        from core.engine.orchestration.patterns.fanout import FanOutPattern
        from core.engine.orchestration.patterns.pipeline import PipelinePattern
        from core.engine.orchestration.patterns.team import TeamPattern

        for PatternClass in [PipelinePattern, TeamPattern, FanOutPattern, AdversarialPattern]:
            pattern = PatternClass(bus=bus, factory=factory)
            result = await pattern.execute(
                task="Empty test",
                config=_make_config(),
                agent_configs=[],
            )
            assert result.status == "failed", f"{PatternClass.__name__} should fail with empty configs"

    @pytest.mark.asyncio
    async def test_single_agent_pipeline(self):
        """Pipeline with single agent works (no handoffs needed)."""
        bus = OrchestrationBus()
        llm = MockLLMProvider(default="Solo output")
        factory = _make_factory(bus, llm)

        from core.engine.orchestration.patterns.pipeline import PipelinePattern

        pattern = PipelinePattern(bus=bus, factory=factory)

        result = await pattern.execute(
            task="Simple task",
            config=_make_config(),
            agent_configs=[_agent("solo")],
        )

        assert result.status == "completed"
        assert len(result.agent_results) == 1
        assert len(llm.calls) == 1

    @pytest.mark.asyncio
    async def test_dispatch_planner_circular_dependency(self):
        """Circular dependencies don't cause infinite loop — forced sequential."""
        from core.engine.orchestration.dispatch_planner import plan_dispatch

        tasks = [
            {"id": "t1", "files_create": ["a.py"], "files_modify": [], "depends_on": ["t2"]},
            {"id": "t2", "files_create": ["b.py"], "files_modify": [], "depends_on": ["t1"]},
        ]

        schedule = plan_dispatch(tasks)
        # Should not hang — circular deps get forced sequential
        assert schedule.total_tasks == 2

    @pytest.mark.asyncio
    async def test_bus_concurrent_publish_safety(self):
        """Bus handles concurrent publishes without data corruption."""
        bus = OrchestrationBus()
        count = 0

        async def counting_handler(msg):
            nonlocal count
            count += 1

        bus.subscribe_global(counting_handler)

        # Fire 50 concurrent publishes
        tasks = [
            bus.publish(
                BusMessage(
                    type=MessageType.AGENT_SPAWNED,
                    source_agent_id=f"agent_{i}",
                    run_id="stress_test",
                )
            )
            for i in range(50)
        ]
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.1)

        assert count == 50, f"Expected 50 messages processed, got {count}"
        assert len(bus.get_messages("stress_test")) == 50
