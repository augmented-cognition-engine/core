# tests/test_engagement.py
"""Tests for multi-spin engagement execution engine."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.orchestrator.engagement_models import EngagementResult, SpinOutput

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_spin_output(**overrides) -> SpinOutput:
    defaults = {
        "content": "Test content",
        "handoff": "Handing off to next perspective",
        "confidence": 0.85,
        "open_questions": ["What about edge cases?"],
        "perspective": "practitioner",
        "specialties_used": ["python-testing"],
    }
    defaults.update(overrides)
    return SpinOutput(**defaults)


_SAMPLE_CLASSIFICATION = {
    "domain_path": "architecture",
    "archetype": "executor",
    "mode": "reactive",
    "complexity": "moderate",
    "perspective": "practitioner",
    "specialties": ["python-testing"],
    "org_context": ["architecture"],
    "engagement": {
        "perspectives": ["practitioner"],
        "adversarial_pair": None,
        "rationale": "Single perspective suffices",
    },
}


_PIPELINE_CLASSIFICATION = {
    "domain_path": "architecture",
    "archetype": "executor",
    "mode": "deliberative",
    "complexity": "complex",
    "perspective": "theorist",
    "specialties": ["distributed-systems"],
    "org_context": ["architecture"],
    "engagement": {
        "perspectives": ["theorist", "practitioner"],
        "adversarial_pair": None,
        "rationale": "Ground theory then build",
    },
}


# ---------------------------------------------------------------------------
# PERSPECTIVE_FRAMING
# ---------------------------------------------------------------------------


class TestPerspectiveFraming:
    def test_perspective_framing_covers_all(self):
        from core.engine.orchestrator.engagement import PERSPECTIVE_FRAMING

        assert "theorist" in PERSPECTIVE_FRAMING
        assert "strategist" in PERSPECTIVE_FRAMING
        assert "practitioner" in PERSPECTIVE_FRAMING
        assert "operator" in PERSPECTIVE_FRAMING
        assert len(PERSPECTIVE_FRAMING) == 4
        for key, value in PERSPECTIVE_FRAMING.items():
            assert isinstance(value, str)
            assert len(value) > 10  # non-trivial framing string


# ---------------------------------------------------------------------------
# _build_spin_prompt
# ---------------------------------------------------------------------------


class TestBuildSpinPrompt:
    def test_build_spin_prompt_first_spin(self):
        from core.engine.orchestrator.engagement import _build_spin_prompt

        prompt = _build_spin_prompt(
            task="Design an auth module",
            perspective="practitioner",
            prior_handoff=None,
            prior_questions=None,
        )

        assert "Design an auth module" in prompt
        assert "practitioner" in prompt.lower() or "implementation" in prompt.lower()
        # No handoff section for first spin
        assert "prior perspective" not in prompt.lower() or "none" in prompt.lower()

    def test_build_spin_prompt_with_handoff(self):
        from core.engine.orchestrator.engagement import _build_spin_prompt

        prompt = _build_spin_prompt(
            task="Design an auth module",
            perspective="practitioner",
            prior_handoff="The theorist identified JWT as the foundation.",
            prior_questions=["What about token rotation?", "How to handle revocation?"],
        )

        assert "Design an auth module" in prompt
        assert "JWT as the foundation" in prompt
        assert "token rotation" in prompt
        assert "revocation" in prompt


# ---------------------------------------------------------------------------
# _build_adversarial_synthesis_prompt
# ---------------------------------------------------------------------------


class TestBuildAdversarialSynthesisPrompt:
    def test_build_adversarial_synthesis_prompt(self):
        from core.engine.orchestrator.engagement import _build_adversarial_synthesis_prompt

        spin_a = _make_spin_output(perspective="theorist", content="Theory says X")
        spin_b = _make_spin_output(perspective="strategist", content="Strategy says Y")

        prompt = _build_adversarial_synthesis_prompt(
            task="Evaluate database options",
            spin_a=spin_a,
            spin_b=spin_b,
        )

        assert "Evaluate database options" in prompt
        assert "Theory says X" in prompt
        assert "Strategy says Y" in prompt
        assert "theorist" in prompt.lower()
        assert "strategist" in prompt.lower()


# ---------------------------------------------------------------------------
# classify_spin
# ---------------------------------------------------------------------------


class TestClassifySpin:
    @pytest.mark.asyncio
    async def test_classify_spin_returns_valid_classification(self):
        from core.engine.orchestrator.engagement import classify_spin

        mock_result = {
            "archetype": "analyst",
            "mode": "deliberative",
            "specialties": ["data-modeling"],
        }

        with patch("core.engine.orchestrator.engagement.llm") as mock_llm:
            mock_llm.complete_json = AsyncMock(return_value=mock_result)
            result = await classify_spin(
                task_description="Analyze data patterns",
                perspective="theorist",
                prior_handoff="Previous analysis showed gaps",
                product_id="product:test",
            )

        assert result["archetype"] == "analyst"
        assert result["mode"] == "deliberative"
        assert result["specialties"] == ["data-modeling"]


# ---------------------------------------------------------------------------
# synthesize_spins
# ---------------------------------------------------------------------------


class TestSynthesizeSpins:
    @pytest.mark.asyncio
    async def test_synthesize_spins_single(self):
        """Single spin returns content directly — no LLM call."""
        from core.engine.orchestrator.engagement import synthesize_spins

        spin = _make_spin_output(content="Direct answer here")

        with patch("core.engine.orchestrator.engagement.llm") as mock_llm:
            result = await synthesize_spins([spin], "Some task")
            mock_llm.complete.assert_not_called()

        assert result == "Direct answer here"

    @pytest.mark.asyncio
    async def test_synthesize_spins_multiple(self):
        """Multiple spins trigger LLM synthesis."""
        from core.engine.orchestrator.engagement import synthesize_spins

        spins = [
            _make_spin_output(perspective="theorist", content="Theory content"),
            _make_spin_output(perspective="practitioner", content="Practice content"),
        ]

        with patch("core.engine.orchestrator.engagement.llm") as mock_llm:
            mock_llm.complete = AsyncMock(return_value="Synthesized output")
            result = await synthesize_spins(spins, "Some task")

        assert result == "Synthesized output"
        mock_llm.complete.assert_called_once()
        prompt = mock_llm.complete.call_args[0][0]
        assert "Theory content" in prompt
        assert "Practice content" in prompt


# ---------------------------------------------------------------------------
# execute_engagement
# ---------------------------------------------------------------------------


class TestExecuteEngagement:
    @pytest.mark.asyncio
    async def test_execute_engagement_single_spin(self):
        """Single-perspective engagement returns spin content directly."""
        from core.engine.orchestrator.engagement import execute_engagement

        spin_output = _make_spin_output(
            perspective="practitioner",
            content="Here is the implementation",
            specialties_used=["python-testing"],
        )

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                new_callable=AsyncMock,
                return_value=spin_output,
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            result = await execute_engagement(
                task_description="Build a test suite",
                classification=_SAMPLE_CLASSIFICATION,
                product_id="product:test",
            )

        assert isinstance(result, EngagementResult)
        assert len(result.spins) == 1
        assert result.merged_output == "Here is the implementation"
        assert result.perspectives_used == ["practitioner"]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_engagement_pipeline(self):
        """Two-perspective pipeline passes handoff from first to second."""
        from core.engine.orchestrator.engagement import execute_engagement

        theorist_spin = _make_spin_output(
            perspective="theorist",
            content="Theoretical foundation",
            handoff="Consider CAP theorem implications",
            open_questions=["What consistency model?"],
        )
        practitioner_spin = _make_spin_output(
            perspective="practitioner",
            content="Implementation plan",
            handoff="Ready for delivery",
        )

        call_count = 0

        async def mock_execute_spin(
            task_description,
            perspective,
            prior_handoff,
            prior_questions,
            classification,
            product_id,
            event_callback=None,
            snapshot=None,
            budget_multiplier=1.0,
        ):
            nonlocal call_count
            call_count += 1
            if perspective == "theorist":
                assert prior_handoff is None
                return theorist_spin
            elif perspective == "practitioner":
                assert prior_handoff == "Consider CAP theorem implications"
                assert prior_questions == ["What consistency model?"]
                return practitioner_spin
            raise ValueError(f"Unexpected perspective: {perspective}")

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                side_effect=mock_execute_spin,
            ),
            patch(
                "core.engine.orchestrator.engagement.synthesize_spins",
                new_callable=AsyncMock,
                return_value="Unified output",
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            result = await execute_engagement(
                task_description="Design a distributed cache",
                classification=_PIPELINE_CLASSIFICATION,
                product_id="product:test",
            )

        assert isinstance(result, EngagementResult)
        assert len(result.spins) == 2
        assert result.perspectives_used == ["theorist", "practitioner"]
        assert result.merged_output == "Unified output"
        assert call_count == 2


# ---------------------------------------------------------------------------
# Quick wins from research papers (MAD + CoALA)
# ---------------------------------------------------------------------------


class TestAdversarialAnalysis:
    """Tests for adaptive termination and diversity metric."""

    def test_compute_spin_diversity_identical(self):
        from core.engine.orchestrator.engagement import compute_spin_diversity

        a = SpinOutput(content="X", handoff="same key points", confidence=0.9, perspective="theorist")
        b = SpinOutput(content="Y", handoff="same key points", confidence=0.8, perspective="practitioner")
        assert compute_spin_diversity(a, b) == 0.0

    def test_compute_spin_diversity_different(self):
        from core.engine.orchestrator.engagement import compute_spin_diversity

        a = SpinOutput(content="X", handoff="theory says use LRU caching", confidence=0.9, perspective="theorist")
        b = SpinOutput(content="Y", handoff="build a Redis cluster instead", confidence=0.8, perspective="practitioner")
        diversity = compute_spin_diversity(a, b)
        assert diversity > 0.3  # meaningfully different

    def test_compute_spin_diversity_empty_handoff(self):
        from core.engine.orchestrator.engagement import compute_spin_diversity

        a = SpinOutput(content="X", handoff="", confidence=0.9, perspective="theorist")
        b = SpinOutput(content="Y", handoff="something", confidence=0.8, perspective="practitioner")
        assert compute_spin_diversity(a, b) == 1.0

    def test_should_skip_synthesis_when_agreeing(self):
        from core.engine.orchestrator.engagement import should_skip_synthesis

        a = SpinOutput(content="X", handoff="use caching for performance", confidence=0.9, perspective="theorist")
        b = SpinOutput(content="Y", handoff="use caching for performance", confidence=0.8, perspective="practitioner")
        assert should_skip_synthesis(a, b) is True

    def test_should_not_skip_synthesis_when_disagreeing(self):
        from core.engine.orchestrator.engagement import should_skip_synthesis

        a = SpinOutput(
            content="X", handoff="theory demands formal verification", confidence=0.9, perspective="theorist"
        )
        b = SpinOutput(
            content="Y", handoff="just ship it with integration tests", confidence=0.8, perspective="practitioner"
        )
        assert should_skip_synthesis(a, b) is False

    def test_adversarial_synthesis_prompt_contains_seek_truth(self):
        from core.engine.orchestrator.engagement import _build_adversarial_synthesis_prompt

        a = SpinOutput(content="Theory", handoff="", confidence=0.9, perspective="theorist")
        b = SpinOutput(content="Practice", handoff="", confidence=0.8, perspective="practitioner")
        prompt = _build_adversarial_synthesis_prompt("test task", a, b)
        assert "seek truth" in prompt.lower()


# ---------------------------------------------------------------------------
# ARCHETYPE_FRAMING
# ---------------------------------------------------------------------------


class TestArchetypeFraming:
    def test_archetype_framing_covers_all_archetypes(self):
        from core.engine.orchestrator.engagement import ARCHETYPE_FRAMING

        archetype_names = {"analyst", "creator", "executor", "researcher", "advisor", "sentinel"}
        for name in archetype_names:
            assert name in ARCHETYPE_FRAMING, f"archetype '{name}' missing from ARCHETYPE_FRAMING"
            assert isinstance(ARCHETYPE_FRAMING[name], str)
            assert len(ARCHETYPE_FRAMING[name]) > 10

    def test_archetype_framing_covers_legacy_perspective_names(self):
        from core.engine.orchestrator.engagement import ARCHETYPE_FRAMING

        legacy_names = {"theorist", "strategist", "practitioner", "operator"}
        for name in legacy_names:
            assert name in ARCHETYPE_FRAMING, f"legacy perspective '{name}' missing from ARCHETYPE_FRAMING"
            assert isinstance(ARCHETYPE_FRAMING[name], str)
            assert len(ARCHETYPE_FRAMING[name]) > 10

    def test_perspective_framing_still_has_four_entries(self):
        """PERSPECTIVE_FRAMING is unchanged — backward compat."""
        from core.engine.orchestrator.engagement import PERSPECTIVE_FRAMING

        assert len(PERSPECTIVE_FRAMING) == 4
        for name in ("theorist", "strategist", "practitioner", "operator"):
            assert name in PERSPECTIVE_FRAMING


# ---------------------------------------------------------------------------
# _build_spin_prompt with archetype names
# ---------------------------------------------------------------------------


class TestBuildSpinPromptArchetypes:
    def test_build_spin_prompt_uses_archetype_framing_for_analyst(self):
        from core.engine.orchestrator.engagement import ARCHETYPE_FRAMING, _build_spin_prompt

        prompt = _build_spin_prompt(
            task="Analyse query latency spikes",
            perspective="analyst",
            prior_handoff=None,
            prior_questions=None,
        )

        assert "Analyse query latency spikes" in prompt
        assert "analyst" in prompt.lower()
        # Framing text should appear in the prompt
        framing_snippet = ARCHETYPE_FRAMING["analyst"][:30]
        assert framing_snippet in prompt

    def test_build_spin_prompt_uses_archetype_framing_for_sentinel(self):
        from core.engine.orchestrator.engagement import ARCHETYPE_FRAMING, _build_spin_prompt

        prompt = _build_spin_prompt(
            task="Review this payment flow for vulnerabilities",
            perspective="sentinel",
            prior_handoff=None,
            prior_questions=None,
        )

        assert "sentinel" in prompt.lower()
        framing_snippet = ARCHETYPE_FRAMING["sentinel"][:30]
        assert framing_snippet in prompt

    def test_build_spin_prompt_uses_archetype_framing_for_creator(self):
        from core.engine.orchestrator.engagement import ARCHETYPE_FRAMING, _build_spin_prompt

        prompt = _build_spin_prompt(
            task="Brainstorm a new onboarding experience",
            perspective="creator",
            prior_handoff=None,
            prior_questions=None,
        )

        assert "creator" in prompt.lower()
        framing_snippet = ARCHETYPE_FRAMING["creator"][:30]
        assert framing_snippet in prompt

    def test_build_spin_prompt_backward_compat_with_theorist(self):
        """Legacy perspective name 'theorist' still resolves correctly."""
        from core.engine.orchestrator.engagement import ARCHETYPE_FRAMING, _build_spin_prompt

        prompt = _build_spin_prompt(
            task="Explain CAP theorem",
            perspective="theorist",
            prior_handoff=None,
            prior_questions=None,
        )

        assert "theorist" in prompt.lower()
        framing_snippet = ARCHETYPE_FRAMING["theorist"][:30]
        assert framing_snippet in prompt


# ---------------------------------------------------------------------------
# run_engagement_with_archetypes
# ---------------------------------------------------------------------------


class TestRunEngagementWithArchetypes:
    @pytest.mark.asyncio
    async def test_run_engagement_with_archetypes_single(self):
        """Single-archetype engagement returns spin content directly."""
        from core.engine.orchestrator.engagement import run_engagement_with_archetypes

        spin_output = _make_spin_output(
            perspective="analyst",
            content="Analysis complete",
            specialties_used=[],
        )

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                new_callable=AsyncMock,
                return_value=spin_output,
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            result = await run_engagement_with_archetypes(
                task_description="Analyse this dataset",
                archetypes=["analyst"],
                product_id="product:test",
            )

        assert isinstance(result, EngagementResult)
        assert len(result.spins) == 1
        assert result.merged_output == "Analysis complete"
        assert result.perspectives_used == ["analyst"]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_run_engagement_with_archetypes_multi(self):
        """Multi-archetype pipeline produces multi-spin result."""
        from core.engine.orchestrator.engagement import run_engagement_with_archetypes

        analyst_spin = _make_spin_output(
            perspective="analyst",
            content="Analysis done",
            handoff="Patterns identified",
            open_questions=["What threshold?"],
        )
        sentinel_spin = _make_spin_output(
            perspective="sentinel",
            content="Risks flagged",
            handoff="Ready",
        )

        call_order: list[str] = []

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
        ):
            call_order.append(perspective)
            if perspective == "analyst":
                return analyst_spin
            return sentinel_spin

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                side_effect=mock_spin,
            ),
            patch(
                "core.engine.orchestrator.engagement.synthesize_spins",
                new_callable=AsyncMock,
                return_value="Unified output",
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            result = await run_engagement_with_archetypes(
                task_description="Review the billing pipeline",
                archetypes=["analyst", "sentinel"],
                product_id="product:test",
            )

        assert isinstance(result, EngagementResult)
        assert len(result.spins) == 2
        assert call_order == ["analyst", "sentinel"]
        assert result.merged_output == "Unified output"

    @pytest.mark.asyncio
    async def test_run_engagement_with_archetypes_invalid_name_falls_back(self):
        """Unknown archetype names are dropped; falls back to executor."""
        from core.engine.orchestrator.engagement import run_engagement_with_archetypes

        spin_output = _make_spin_output(perspective="executor", content="Done")

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                new_callable=AsyncMock,
                return_value=spin_output,
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            result = await run_engagement_with_archetypes(
                task_description="Do something",
                archetypes=["unknown_archetype"],
                product_id="product:test",
            )

        assert isinstance(result, EngagementResult)
        assert len(result.spins) == 1


# ---------------------------------------------------------------------------
# run_engagement (backward compat wrapper)
# ---------------------------------------------------------------------------


class TestRunEngagementBackwardCompat:
    @pytest.mark.asyncio
    async def test_run_engagement_with_perspective_names(self):
        """Legacy run_engagement() with perspective names still works."""
        from core.engine.orchestrator.engagement import run_engagement

        spin_output = _make_spin_output(
            perspective="practitioner",
            content="Implementation ready",
            specialties_used=[],
        )

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                new_callable=AsyncMock,
                return_value=spin_output,
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            result = await run_engagement(
                task_description="Build the feature",
                perspectives=["practitioner"],
                product_id="product:test",
            )

        assert isinstance(result, EngagementResult)
        assert result.merged_output == "Implementation ready"

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_run_engagement_mixed_names(self):
        """run_engagement accepts a mix of perspective and archetype names."""
        from core.engine.orchestrator.engagement import run_engagement

        theorist_spin = _make_spin_output(perspective="theorist", content="Theory", handoff="T")
        executor_spin = _make_spin_output(perspective="executor", content="Done", handoff="E")

        call_order: list[str] = []

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
        ):
            call_order.append(perspective)
            return theorist_spin if perspective == "theorist" else executor_spin

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                side_effect=mock_spin,
            ),
            patch(
                "core.engine.orchestrator.engagement.synthesize_spins",
                new_callable=AsyncMock,
                return_value="Mixed output",
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            result = await run_engagement(
                task_description="Design and build",
                perspectives=["theorist", "executor"],
                product_id="product:test",
            )

        assert len(result.spins) == 2
        assert call_order == ["theorist", "executor"]
