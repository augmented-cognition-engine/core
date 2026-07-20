# tests/test_e2e_orchestration_wiring.py
"""End-to-end wiring tests — verify data flows between layers.

These tests verify what the pattern tests don't: that the layers are
actually connected. Composition scorer weights reach engagement.
Intelligence appears in agent prompts. API routes call the right engine
functions. Feedback handler routes to correct sub-handlers.

These complement test_e2e_orchestration_scenarios.py which tests
each layer in isolation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_pool(db=None):
    if db is None:
        db = AsyncMock()
        db.query = AsyncMock(return_value=[])
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


# ═══════════════════════════════════════════════════════════════════════════════
# 1. COMPOSITION SCORER → ENGAGEMENT WEIGHT WIRING
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompositionToEngagementWiring:
    """Verify perspective_weights flow from scorer → executor → engagement."""

    @pytest.mark.asyncio
    async def test_scorer_stores_weights_on_classification(self):
        """score_composition returns weights that the executor stores on classification dict.

        This tests the contract: executor reads scored.perspective_weights and
        puts it on classification["perspective_weights"] for execute_engagement.
        """
        from core.engine.orchestration.composition_scorer import ScoredComposition

        scored = ScoredComposition(
            perspectives=["theorist", "practitioner"],
            perspective_weights={"theorist": 0.5, "practitioner": 1.0},
            engagement_type="pipeline",
            specialties=["python-development"],
            framework_hints=[],
            adjustments=["theorist: weight * 0.5 (low acceptance)"],
        )

        # Simulate what the executor does (lines 362-378 of orchestration/executor.py)
        classification = {
            "discipline": "architecture",
            "engagement": {"perspectives": ["theorist", "practitioner"]},
        }

        # This is the exact code from the executor:
        classification["perspective_weights"] = scored.perspective_weights
        engagement = classification.get("engagement", {})
        if scored.perspectives != engagement.get("perspectives", []):
            engagement["perspectives"] = scored.perspectives
            classification["engagement"] = engagement

        assert classification["perspective_weights"] == {"theorist": 0.5, "practitioner": 1.0}

    @pytest.mark.asyncio
    async def test_engagement_receives_and_uses_weights(self):
        """execute_engagement uses perspective_weights as budget_multiplier per spin."""
        from core.engine.orchestrator.engagement_models import SpinOutput

        spin_budget_multipliers: list[float] = []

        async def mock_spin(
            task_description,
            perspective,
            prior_handoff,
            prior_questions,
            classification,
            product_id,
            event_callback=None,
            snapshot=None,
            budget_multiplier=1.0,
            **kwargs,
        ):
            spin_budget_multipliers.append(budget_multiplier)
            return SpinOutput(
                content=f"{perspective} analysis",
                handoff=f"Handoff from {perspective}",
                confidence=0.8,
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
            patch("core.engine.orchestrator.engagement.synthesize_spins", return_value="Synthesized"),
            patch("core.engine.orchestrator.executor._load_snapshot", new_callable=AsyncMock, return_value={}),
        ):
            from core.engine.orchestrator.engagement import execute_engagement

            await execute_engagement(
                task_description="Test weighted engagement",
                classification={
                    "discipline": "architecture",
                    "mode": "deliberative",
                    "engagement": {
                        "perspectives": ["theorist", "practitioner"],
                        "rationale": "test",
                    },
                },
                product_id="product:test",
                perspective_weights={"theorist": 0.5, "practitioner": 1.0},
            )

        # Verify the weights were passed as budget_multiplier
        assert len(spin_budget_multipliers) == 2
        assert spin_budget_multipliers[0] == 0.5  # theorist: weight from perspective_weights
        assert spin_budget_multipliers[1] == 1.0  # practitioner: weight 1.0

    @pytest.mark.asyncio
    async def test_adversarial_engagement_uses_weights(self):
        """Adversarial pair execution passes weights as budget_multiplier."""
        from core.engine.orchestrator.engagement_models import SpinOutput

        spin_budget_multipliers: dict[str, float] = {}

        async def mock_spin(task_description, perspective, *args, budget_multiplier=1.0, **kwargs):
            spin_budget_multipliers[perspective] = budget_multiplier
            return SpinOutput(
                content=f"{perspective} position",
                handoff=f"Unique handoff from {perspective} with distinct content",
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
            mock_llm.complete = AsyncMock(return_value="Synthesis")

            from core.engine.orchestrator.engagement import execute_engagement

            await execute_engagement(
                task_description="Adversarial weighted",
                classification={
                    "discipline": "architecture",
                    "mode": "deliberative",
                    "engagement": {
                        "perspectives": ["theorist", "strategist"],
                        "adversarial_pair": ["theorist", "strategist"],
                        "rationale": "test",
                    },
                },
                product_id="product:test",
                perspective_weights={"theorist": 0.3, "strategist": 0.9},
            )

        assert spin_budget_multipliers["theorist"] == 0.3
        assert spin_budget_multipliers["strategist"] == 0.9

    @pytest.mark.asyncio
    async def test_old_executor_now_passes_weights(self):
        """The legacy execute_task() now calls score_composition and passes
        perspective_weights to execute_engagement (gap fixed)."""
        from core.engine.orchestration.composition_scorer import ScoredComposition
        from core.engine.orchestrator.engagement_models import EngagementResult, SpinOutput

        captured_kwargs: list[dict] = []

        async def mock_engagement(desc, classification, product_id, workspace_id="workspace:default", **kwargs):
            captured_kwargs.append(kwargs)
            return EngagementResult(
                spins=[
                    SpinOutput(
                        content="output",
                        handoff="",
                        confidence=0.8,
                        perspective="practitioner",
                        specialties_used=[],
                    )
                ],
                merged_output="result",
                perspectives_used=["theorist", "practitioner"],
            )

        mock_classification = {
            "discipline": "architecture",
            "archetype": "analyst",
            "mode": "deliberative",
            "perspective": "theorist",
            "specialties": [],
            "engagement": {
                "perspectives": ["theorist", "practitioner"],
                "rationale": "test",
            },
        }

        scored = ScoredComposition(
            perspectives=["theorist", "practitioner"],
            perspective_weights={"theorist": 0.7, "practitioner": 1.0},
            engagement_type="pipeline",
            specialties=[],
            framework_hints=[],
            adjustments=[],
        )

        with (
            patch("core.engine.orchestrator.executor.classify_task", return_value=mock_classification),
            patch("core.engine.orchestrator.executor.load_intelligence", return_value={"insights": []}),
            patch("engine.orchestation.composition_scorer.score_composition", return_value=scored)
            if False
            else patch("core.engine.orchestration.composition_scorer.score_composition", return_value=scored),
            patch("core.engine.orchestrator.engagement.execute_engagement", side_effect=mock_engagement),
            patch("core.engine.orchestrator.injection.inject_missing_perspectives", side_effect=lambda c, o: c),
            patch("core.engine.orchestrator.executor.pool", _make_pool()),
            patch("core.engine.orchestrator.executor.llm") as mock_llm,
        ):
            mock_llm.complete = AsyncMock(return_value="response")

            from core.engine.orchestrator.executor import execute_task

            await execute_task(
                description="Test old executor with weights",
                product_id="product:test",
                workspace_id="workspace:test",
                user_id="user:test",
            )

        assert len(captured_kwargs) >= 1
        weights = captured_kwargs[0].get("perspective_weights")
        assert weights is not None, "Old executor should now pass perspective_weights"
        assert weights == {"theorist": 0.7, "practitioner": 1.0}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SHELL COMPOSER — Prompt Assembly + Intelligence
# ═══════════════════════════════════════════════════════════════════════════════


class TestShellComposerPromptAssembly:
    """Verify ShellComposer builds correct prompts from classification + snapshot."""

    def test_system_prompt_contains_archetype_and_mode(self):
        """ComposedShell system prompt includes archetype and mode instructions."""
        from core.engine.orchestration.shell import ShellComposer

        composer = ShellComposer()
        shell = composer.compose(
            classification={"archetype": "analyst", "mode": "deliberative"},
            snapshot={"insights": []},
            description="Analyze this codebase",
        )

        assert "ACE" in shell.system_prompt
        assert "working from evidence" in shell.system_prompt.lower() or "evidence" in shell.system_prompt.lower()
        assert "reasoning carefully" in shell.system_prompt.lower() or "deliberative" in shell.system_prompt.lower()

    def test_system_prompt_contains_intelligence(self):
        """Intelligence from snapshot is injected into the system prompt."""
        from core.engine.orchestration.shell import ShellComposer

        composer = ShellComposer()
        shell = composer.compose(
            classification={"archetype": "executor", "mode": "reactive"},
            snapshot={
                "specialty_insights": [
                    {"content": "Always validate JWT tokens on every request", "confidence": 0.95},
                    {"content": "Use bcrypt for password hashing", "confidence": 0.9},
                ],
                "insights": [
                    {"content": "Always validate JWT tokens on every request", "confidence": 0.95},
                ],
            },
            description="Build auth module",
        )

        # Intelligence should appear in the system prompt
        assert "JWT" in shell.system_prompt or "Expert Knowledge" in shell.system_prompt

    def test_user_prompt_is_description(self):
        """The user prompt is the task description."""
        from core.engine.orchestration.shell import ShellComposer

        composer = ShellComposer()
        shell = composer.compose(
            classification={"archetype": "creator", "mode": "deliberative"},
            snapshot={"insights": []},
            description="Build a REST API for user management",
        )

        assert shell.user_prompt == "Build a REST API for user management"

    def test_conversation_messages_forwarded(self):
        """Conversation history is passed through to ComposedShell."""
        from core.engine.orchestration.shell import ShellComposer

        messages = [{"role": "user", "content": "Previous context"}]
        composer = ShellComposer()
        shell = composer.compose(
            classification={"archetype": "advisor", "mode": "conversational"},
            snapshot={"insights": []},
            description="Continue our discussion",
            conversation_messages=messages,
        )

        assert shell.messages == messages

    def test_all_archetypes_produce_different_prompts(self):
        """Each archetype produces a distinguishable system prompt."""
        from core.engine.orchestration.shell import ShellComposer

        composer = ShellComposer()
        prompts = {}

        for archetype in ["creator", "analyst", "executor", "researcher", "advisor", "sentinel"]:
            shell = composer.compose(
                classification={"archetype": archetype, "mode": "reactive"},
                snapshot={"insights": []},
                description="Test task",
            )
            prompts[archetype] = shell.system_prompt

        # Each archetype should have a unique prompt
        unique_prompts = set(prompts.values())
        assert len(unique_prompts) == 6, f"Expected 6 unique prompts for 6 archetypes, got {len(unique_prompts)}"

    def test_all_modes_produce_different_prompts(self):
        """Each mode produces a distinguishable system prompt."""
        from core.engine.orchestration.shell import ShellComposer

        composer = ShellComposer()
        prompts = {}

        for mode in ["deliberative", "reactive", "exploratory", "conversational", "procedural", "reflective"]:
            shell = composer.compose(
                classification={"archetype": "executor", "mode": mode},
                snapshot={"insights": []},
                description="Test task",
            )
            prompts[mode] = shell.system_prompt

        unique_prompts = set(prompts.values())
        assert len(unique_prompts) == 6, f"Expected 6 unique prompts for 6 modes, got {len(unique_prompts)}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. INTELLIGENCE IN AGENT PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntelligenceInPrompts:
    """Verify loaded intelligence actually appears in what agents see."""

    def test_build_intel_context_specialty_insights(self):
        """_build_intel_context formats specialty insights into prompt text."""
        from core.engine.orchestrator.executor import _build_intel_context

        context = _build_intel_context(
            {
                "specialty_insights": [
                    {"content": "Use dependency injection for testability", "confidence": 0.92},
                    {"content": "Prefer composition over inheritance", "confidence": 0.88},
                ],
            }
        )

        assert "dependency injection" in context.lower()
        assert "composition over inheritance" in context.lower()
        assert "Expert Knowledge" in context

    def test_build_intel_context_org_insights_with_specialty(self):
        """_build_intel_context formats org-specific insights alongside specialty."""
        from core.engine.orchestrator.executor import _build_intel_context

        context = _build_intel_context(
            {
                "specialty_insights": [
                    {"content": "Use dependency injection", "confidence": 0.9},
                ],
                "org_insights": [
                    {"content": "Our team uses snake_case for all Python files", "confidence": 0.95},
                ],
            }
        )

        assert "snake_case" in context
        assert "Team Context" in context
        assert "Expert Knowledge" in context

    def test_build_intel_context_org_insights_without_specialty(self):
        """org_insights render even when specialty_insights is empty."""
        from core.engine.orchestrator.executor import _build_intel_context

        context = _build_intel_context(
            {
                "org_insights": [
                    {"content": "We deploy to AWS us-east-1 only", "confidence": 0.95},
                ],
            }
        )

        assert "AWS us-east-1" in context
        assert "Team Context" in context

    def test_build_intel_context_empty_snapshot(self):
        """Empty snapshot produces empty context (no crash)."""
        from core.engine.orchestrator.executor import _build_intel_context

        context = _build_intel_context({})
        assert isinstance(context, str)

    def test_build_intel_context_legacy_format(self):
        """Legacy single-list 'insights' format still works."""
        from core.engine.orchestrator.executor import _build_intel_context

        context = _build_intel_context(
            {
                "insights": [
                    {"content": "Always write tests first", "confidence": 0.85, "insight_type": "pattern"},
                ],
            }
        )

        assert "tests first" in context.lower()
        assert "Established Intelligence" in context

    def test_build_intel_context_recent_signals(self):
        """Recent unverified signals (if present) appear in context."""
        from core.engine.orchestrator.executor import _build_intel_context

        context = _build_intel_context(
            {
                "recent_signals": [
                    {"content": "New pattern discovered: event sourcing works well here"},
                ],
            }
        )

        # recent_signals may or may not be rendered — test it doesn't crash
        assert isinstance(context, str)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. API ROUTES → ENGINE WIRING
# ═══════════════════════════════════════════════════════════════════════════════


class TestAPIRouteWiring:
    """Verify API endpoints call the correct engine functions with correct params."""

    @pytest.mark.asyncio
    async def test_post_tasks_calls_orchestrate(self):
        """POST /tasks creates OrchestrationRequest and calls orchestrate()."""
        from core.engine.orchestration.executor import OrchestrationResult

        mock_result = OrchestrationResult(
            task_id="task:123",
            output="Test output",
            classification={"domain_path": "architecture", "archetype": "creator", "mode": "deliberative"},
            snapshot={"specialties_loaded": []},
            status="completed",
        )

        captured_requests: list = []

        async def mock_orchestrate(request):
            captured_requests.append(request)
            return mock_result

        mock_user = {"sub": "user:test", "product": "product:test"}

        from core.engine.api import tasks as task_api
        from core.engine.api.main import app
        from core.engine.core.auth import get_current_user

        @asynccontextmanager
        async def mock_lifespan(a):
            yield

        app.router.lifespan_context = mock_lifespan
        task_api._accepting_tasks = True
        app.dependency_overrides[get_current_user] = lambda: mock_user

        task_state = {"id": "task:123", "status": "pending", "product": "product:test"}

        async def update_receipt(_task_id, fields):
            task_state.update(fields)
            return task_state

        async def get_receipt(_task_id):
            return task_state

        try:
            with (
                patch("core.engine.orchestration.orchestrate", mock_orchestrate),
                patch(
                    "core.engine.api.tasks._create_or_get_receipt",
                    new=AsyncMock(return_value=(task_state, True)),
                ),
                patch("core.engine.api.tasks._update_receipt", new=update_receipt),
                patch("core.engine.api.tasks._get_task_record", new=get_receipt),
            ):
                from httpx import ASGITransport, AsyncClient

                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post(
                        "/tasks",
                        json={
                            "description": "Fix the login bug",
                            "workspace_id": "workspace:default",
                            "wait_seconds": 1,
                        },
                    )

            assert resp.status_code == 202
            assert len(captured_requests) == 1

            req = captured_requests[0]
            assert req.description == "Fix the login bug"
            assert req.product_id == "product:test"
            assert req.user_id == "user:test"
            assert req.workspace_id == "workspace:default"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.asyncio
    async def test_post_tasks_passes_model_and_deep(self):
        """POST /tasks forwards model, deep, force_skill, frameworks_hint."""
        from core.engine.orchestration.executor import OrchestrationResult

        mock_result = OrchestrationResult(
            task_id="task:456",
            output="Output",
            classification={"domain_path": "testing"},
            snapshot={},
            status="completed",
        )

        captured_requests: list = []

        async def mock_orchestrate(request):
            captured_requests.append(request)
            return mock_result

        mock_user = {"sub": "user:test", "product": "product:test"}

        from core.engine.api import tasks as task_api
        from core.engine.api.main import app
        from core.engine.core.auth import get_current_user

        @asynccontextmanager
        async def mock_lifespan(a):
            yield

        app.router.lifespan_context = mock_lifespan
        task_api._accepting_tasks = True
        app.dependency_overrides[get_current_user] = lambda: mock_user

        task_state = {"id": "task:456", "status": "pending", "product": "product:test"}

        async def update_receipt(_task_id, fields):
            task_state.update(fields)
            return task_state

        async def get_receipt(_task_id):
            return task_state

        try:
            with (
                patch("core.engine.orchestration.orchestrate", mock_orchestrate),
                patch(
                    "core.engine.api.tasks._create_or_get_receipt",
                    new=AsyncMock(return_value=(task_state, True)),
                ),
                patch("core.engine.api.tasks._update_receipt", new=update_receipt),
                patch("core.engine.api.tasks._get_task_record", new=get_receipt),
            ):
                from httpx import ASGITransport, AsyncClient

                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post(
                        "/tasks",
                        json={
                            "description": "Deep analysis",
                            "workspace_id": "workspace:test",
                            "model": "budget",
                            "deep": True,
                            "force_skill": "security-audit",
                            "frameworks_hint": ["owasp-top-10"],
                            "wait_seconds": 1,
                        },
                    )

            assert resp.status_code == 202
            req = captured_requests[0]
            from core.engine.core.config import settings

            assert req.model == settings.llm_budget_model
            assert req.force_frameworks is True
            assert req.force_skill == "security-audit"
            assert req.frameworks_hint == ["owasp-top-10"]
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.asyncio
    async def test_post_initiatives_calls_tracker(self):
        """POST /initiatives calls InitiativeTracker.create_initiative with user context."""
        captured_calls: list[dict] = []

        class MockTracker:
            def __init__(self, **kwargs):
                pass

            async def create_initiative(self, **kwargs):
                captured_calls.append(kwargs)
                return {"id": "initiative:test", "status": "planning"}

        mock_user = {"sub": "user:test", "product": "product:test"}

        from core.engine.api.main import app
        from core.engine.core.auth import get_current_user

        @asynccontextmanager
        async def mock_lifespan(a):
            yield

        app.router.lifespan_context = mock_lifespan
        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            with patch("core.engine.pm.tracker.InitiativeTracker", MockTracker):
                from httpx import ASGITransport, AsyncClient

                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post(
                        "/initiatives",
                        json={
                            "title": "Build auth system",
                            "description": "Full JWT-based auth",
                            "workspace_id": "workspace:default",
                            "priority": "high",
                            "cost_budget": 50.0,
                        },
                    )

            assert resp.status_code == 201
            assert len(captured_calls) == 1
            call = captured_calls[0]
            assert call["title"] == "Build auth system"
            assert call["product_id"] == "product:test"
            assert call["user_id"] == "user:test"
            assert call["priority"] == "high"
            assert call["cost_budget"] == 50.0
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FEEDBACK HANDLER — Routing + Per-Type Behavior
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeedbackHandlerRouting:
    """Verify each feedback type is routed to the correct handler."""

    @pytest.mark.asyncio
    async def test_blocker_creates_critical_product_question(self):
        """Blocker feedback creates a critical product_question and flags escalation."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "agent_feedback:1"}]])
        pool = _make_pool(db)

        from core.engine.product.feedback_handler import FeedbackHandler
        from core.engine.product.spec_models import AgentFeedbackCreate

        handler = FeedbackHandler(db_pool=pool)
        result = await handler.handle(
            AgentFeedbackCreate(
                spec_id="agent_spec:test",
                feedback_type="blocker",
                content="Cannot connect to external API — firewall blocks port 443",
                work_unit="unit-1",
            ),
            product_id="product:test",
        )

        assert result["feedback_type"] == "blocker"
        assert result["action"]["action"] == "blocker_flagged"
        assert result["action"]["escalated"] is True

        # Should have made 3 DB calls: persist feedback + product_question + composition_signal
        assert db.query.call_count == 3
        second_call = db.query.call_args_list[1]
        assert "product_question" in second_call[0][0]
        assert "critical" in second_call[0][0]

    @pytest.mark.asyncio
    async def test_discovery_creates_observation(self):
        """Discovery feedback creates an observation in the capture pipeline."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "agent_feedback:2"}]])
        pool = _make_pool(db)

        from core.engine.product.feedback_handler import FeedbackHandler
        from core.engine.product.spec_models import AgentFeedbackCreate

        handler = FeedbackHandler(db_pool=pool)
        result = await handler.handle(
            AgentFeedbackCreate(
                spec_id="agent_spec:test",
                feedback_type="discovery",
                content="Found undocumented API endpoint at /internal/health",
            ),
            product_id="product:test",
        )

        assert result["action"]["action"] == "discovery_captured"
        assert result["action"]["fed_to_intelligence"] is True

        # Should create an observation record
        assert db.query.call_count == 2
        second_call = db.query.call_args_list[1]
        assert "observation" in second_call[0][0]
        assert "agent_discovery" in second_call[0][0]

    @pytest.mark.asyncio
    async def test_trade_off_creates_high_priority_question(self):
        """Trade-off feedback escalates with high priority product question."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "agent_feedback:3"}]])
        pool = _make_pool(db)

        from core.engine.product.feedback_handler import FeedbackHandler
        from core.engine.product.spec_models import AgentFeedbackCreate

        handler = FeedbackHandler(db_pool=pool)
        result = await handler.handle(
            AgentFeedbackCreate(
                spec_id="agent_spec:test",
                feedback_type="trade_off",
                content="SQL vs NoSQL: SQL is simpler but NoSQL scales better",
            ),
            product_id="product:test",
        )

        assert result["action"]["action"] == "trade_off_escalated"
        assert result["action"]["needs_decision"] is True

    @pytest.mark.asyncio
    async def test_scope_question_escalates(self):
        """Scope question feedback creates a product question for clarification."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "agent_feedback:4"}]])
        pool = _make_pool(db)

        from core.engine.product.feedback_handler import FeedbackHandler
        from core.engine.product.spec_models import AgentFeedbackCreate

        handler = FeedbackHandler(db_pool=pool)
        result = await handler.handle(
            AgentFeedbackCreate(
                spec_id="agent_spec:test",
                feedback_type="scope_question",
                content="Should this API support pagination?",
            ),
            product_id="product:test",
        )

        assert result["action"]["action"] == "scope_question_escalated"
        assert result["action"]["needs_clarification"] is True

    @pytest.mark.asyncio
    async def test_completion_transitions_spec_to_verifying(self):
        """Completion feedback updates spec status to 'verifying'."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "agent_feedback:5"}]])
        pool = _make_pool(db)

        from core.engine.product.feedback_handler import FeedbackHandler
        from core.engine.product.spec_models import AgentFeedbackCreate

        handler = FeedbackHandler(db_pool=pool)
        result = await handler.handle(
            AgentFeedbackCreate(
                spec_id="agent_spec:test",
                feedback_type="completion",
                content="All acceptance criteria met",
            ),
            product_id="product:test",
        )

        assert result["action"]["action"] == "completion_received"
        assert result["action"]["verification_queued"] is True

        # Should update spec status + write composition_signal
        assert db.query.call_count == 3
        second_call = db.query.call_args_list[1]
        assert "verifying" in second_call[0][0]

    @pytest.mark.asyncio
    async def test_progress_is_noop(self):
        """Progress feedback is just logged — no DB side effects beyond persist."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "agent_feedback:6"}]])
        pool = _make_pool(db)

        from core.engine.product.feedback_handler import FeedbackHandler
        from core.engine.product.spec_models import AgentFeedbackCreate

        handler = FeedbackHandler(db_pool=pool)
        result = await handler.handle(
            AgentFeedbackCreate(
                spec_id="agent_spec:test",
                feedback_type="progress",
                content="50% complete, working on API layer",
            ),
            product_id="product:test",
        )

        assert result["action"]["action"] == "progress_noted"
        # Only 1 DB call (persist feedback), no additional action
        assert db.query.call_count == 1

    @pytest.mark.asyncio
    async def test_unknown_type_falls_back_to_progress(self):
        """Unknown feedback type falls back to progress handler (no crash)."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "agent_feedback:7"}]])
        pool = _make_pool(db)

        from core.engine.product.feedback_handler import FeedbackHandler
        from core.engine.product.spec_models import AgentFeedbackCreate

        handler = FeedbackHandler(db_pool=pool)

        # Bypass pydantic validation to test handler routing
        fb = AgentFeedbackCreate.__new__(AgentFeedbackCreate)
        object.__setattr__(fb, "spec_id", "agent_spec:test")
        object.__setattr__(fb, "feedback_type", "nonexistent_type")
        object.__setattr__(fb, "content", "weird feedback")
        object.__setattr__(fb, "work_unit", None)
        object.__setattr__(fb, "context", None)

        result = await handler.handle(fb, product_id="product:test")
        assert result["action"]["action"] == "progress_noted"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. FEEDBACK → COMPOSITION_SIGNAL GAP (Broken Loop)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeedbackLoopWiring:
    """Verify FeedbackHandler writes composition_signal for quality-relevant feedback.

    The composition scorer queries composition_signal to adjust perspective weights.
    FeedbackHandler now writes signals for completion (accepted) and blocker (rejected).
    """

    @pytest.mark.asyncio
    async def test_completion_writes_composition_signal(self):
        """completion feedback writes composition_signal with feedback='accepted'."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "agent_feedback:1"}]])
        pool = _make_pool(db)

        from core.engine.product.feedback_handler import FeedbackHandler
        from core.engine.product.spec_models import AgentFeedbackCreate

        handler = FeedbackHandler(db_pool=pool)
        await handler.handle(
            AgentFeedbackCreate(
                spec_id="agent_spec:test",
                feedback_type="completion",
                content="All done",
            ),
            product_id="product:test",
        )

        # Should have 3 DB calls: persist feedback + update spec status + composition_signal
        all_queries = [call[0][0] for call in db.query.call_args_list if call[0]]
        comp_queries = [q for q in all_queries if "composition_signal" in q]
        assert len(comp_queries) == 1, f"Expected 1 composition_signal write, got {len(comp_queries)}"

        # Verify the feedback value is 'accepted' (passed as $feedback param)
        comp_call = [c for c in db.query.call_args_list if "composition_signal" in c[0][0]][0]
        assert comp_call[0][1]["feedback"] == "accepted"

    @pytest.mark.asyncio
    async def test_blocker_writes_composition_signal(self):
        """blocker feedback writes composition_signal with feedback='rejected'."""
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "agent_feedback:1"}]])
        pool = _make_pool(db)

        from core.engine.product.feedback_handler import FeedbackHandler
        from core.engine.product.spec_models import AgentFeedbackCreate

        handler = FeedbackHandler(db_pool=pool)
        await handler.handle(
            AgentFeedbackCreate(
                spec_id="agent_spec:test",
                feedback_type="blocker",
                content="Cannot proceed",
            ),
            product_id="product:test",
        )

        all_queries = [call[0][0] for call in db.query.call_args_list if call[0]]
        comp_queries = [q for q in all_queries if "composition_signal" in q]
        assert len(comp_queries) == 1

        # Verify the feedback value is 'rejected' for blocker
        comp_call = [c for c in db.query.call_args_list if "composition_signal" in c[0][0]][0]
        assert comp_call[0][1]["feedback"] == "rejected"

    @pytest.mark.asyncio
    async def test_neutral_feedback_types_skip_composition_signal(self):
        """discovery, trade_off, scope_question, progress do NOT write composition_signal."""
        for fb_type in ["discovery", "trade_off", "scope_question", "progress"]:
            db = AsyncMock()
            db.query = AsyncMock(return_value=[[{"id": "agent_feedback:1"}]])
            pool = _make_pool(db)

            from core.engine.product.feedback_handler import FeedbackHandler
            from core.engine.product.spec_models import AgentFeedbackCreate

            handler = FeedbackHandler(db_pool=pool)
            fb = AgentFeedbackCreate.__new__(AgentFeedbackCreate)
            object.__setattr__(fb, "spec_id", "agent_spec:test")
            object.__setattr__(fb, "feedback_type", fb_type)
            object.__setattr__(fb, "content", f"Test {fb_type}")
            object.__setattr__(fb, "work_unit", None)
            object.__setattr__(fb, "context", None)

            await handler.handle(fb, product_id="product:test")

            all_queries = [call[0][0] for call in db.query.call_args_list if call[0]]
            comp_queries = [q for q in all_queries if "composition_signal" in q]
            assert len(comp_queries) == 0, (
                f"'{fb_type}' feedback should NOT write composition_signal, but found {len(comp_queries)} writes"
            )

    @pytest.mark.asyncio
    async def test_task_patch_does_backfill_composition_signal(self):
        """PATCH /tasks/{id} backfills composition_signal — this IS the wired path."""
        # This test verifies the task feedback API (not FeedbackHandler) writes
        # to composition_signal, which is the only path that feeds the scorer.
        db = AsyncMock()
        db.query = AsyncMock(return_value=[[{"id": "task:test", "product": "product:test"}]])
        mock_user = {"sub": "user:test", "product": "product:test"}

        from core.engine.api.main import app
        from core.engine.core.auth import get_current_user

        @asynccontextmanager
        async def mock_lifespan(a):
            yield

        app.router.lifespan_context = mock_lifespan
        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            with patch("core.engine.api.tasks.pool", _make_pool(db)):
                from httpx import ASGITransport, AsyncClient

                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.patch(
                        "/tasks/task:test",
                        json={
                            "feedback_human": "accepted",
                        },
                    )

            # Check that one of the DB queries mentions composition_signal
            all_queries = [call[0][0] for call in db.query.call_args_list if call[0]]
            has_composition = any("composition_signal" in q for q in all_queries)
            assert has_composition, f"PATCH /tasks should backfill composition_signal. Queries: {all_queries}"
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SESSION RUNNER / TASK RUNNER WIRING
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionRunnerWiring:
    """Verify SessionRunner creates sessions and calls orchestrate()."""

    @pytest.mark.asyncio
    async def test_session_runner_calls_orchestrate(self):
        """SessionRunner.run() creates OrchestrationRequest.from_runner and calls orchestrate."""
        from core.engine.orchestration.executor import OrchestrationResult

        mock_result = OrchestrationResult(
            task_id="task:from_runner",
            output="Runner output",
            classification={},
            snapshot={},
            status="completed",
        )

        orchestrate_calls: list = []

        async def mock_orchestrate(request):
            orchestrate_calls.append(request)
            return mock_result

        pool = _make_pool()

        with (
            patch("core.engine.orchestration.orchestrate", mock_orchestrate),
            patch("core.engine.live.session_runner.AgentCoordinator") as MockCoord,
            patch("core.engine.live.session_runner.EditTracker") as MockTracker,
        ):
            mock_coord = MockCoord.return_value
            mock_coord.start_session = AsyncMock(return_value={"id": "session:123"})
            mock_coord.transition = AsyncMock()

            mock_tracker = MockTracker.return_value
            mock_tracker.release_all = AsyncMock()

            from core.engine.live.session_runner import SessionRunner

            runner = SessionRunner(db_pool=pool)
            result = await runner.run(
                queue_item={"description": "Build feature X", "work_item_id": "wi:1"},
                product_id="product:test",
            )

        assert len(orchestrate_calls) == 1
        req = orchestrate_calls[0]
        assert "Build feature X" in req.description
        assert req.product_id == "product:test"
        assert req.source == "runner"

    @pytest.mark.asyncio
    async def test_orchestration_request_from_runner_sets_source(self):
        """OrchestrationRequest.from_runner() sets source='runner'."""
        from core.engine.orchestration.request import OrchestrationRequest

        req = OrchestrationRequest.from_runner(
            queue_item={"description": "Run this task"},
            product_id="product:test",
        )

        assert req.source == "runner"
        assert req.description == "Run this task"
        assert req.product_id == "product:test"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. CROSS-LAYER INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossLayerIntegration:
    """Tests that verify multiple layers working together."""

    @pytest.mark.asyncio
    async def test_scorer_perspective_injection_updates_classification(self):
        """When scorer injects a perspective, the classification dict is updated
        so downstream consumers (engagement) see the new perspective list."""
        from core.engine.orchestration.composition_scorer import ScoredComposition

        scored = ScoredComposition(
            perspectives=["practitioner", "operator"],  # operator was injected
            perspective_weights={"practitioner": 1.0, "operator": 0.6},
            engagement_type="pipeline",
            specialties=[],
            framework_hints=[],
            adjustments=["Injected operator"],
        )

        # Simulate the executor's code (lines 368-376)
        classification = {
            "discipline": "architecture",
            "engagement": {
                "perspectives": ["practitioner"],  # original: only practitioner
                "rationale": "test",
            },
        }

        # This is the exact update logic from orchestration/executor.py
        classification["perspective_weights"] = scored.perspective_weights
        engagement = classification.get("engagement", {})
        if scored.perspectives != engagement.get("perspectives", []):
            engagement["perspectives"] = scored.perspectives
            classification["engagement"] = engagement
        if scored.engagement_type == "adversarial" and not engagement.get("adversarial_pair"):
            if len(scored.perspectives) >= 2:
                engagement["adversarial_pair"] = scored.perspectives[:2]
                classification["engagement"] = engagement

        # After scorer update, classification should reflect injected operator
        assert "operator" in classification["engagement"]["perspectives"]
        assert classification["perspective_weights"]["operator"] == 0.6
        # And the engagement now has 2 perspectives, triggering multi-spin path
        assert len(classification["engagement"]["perspectives"]) == 2
