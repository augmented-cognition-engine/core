"""Regression tests for the light-coverage meta-skills.

Memory, gap, coordination, tool intelligences previously had only 1 test file
each. These tests lock in that each self-nominates correctly on realistic task
descriptions — preventing silent regressions if signals or affinities drift
during future tuning.

The scenarios here mirror scripts/exercise_light_coverage.py — that script is
for ad-hoc exploration; these tests guard the floor.
"""

from __future__ import annotations

import pytest

from core.engine.cognition.composer import CognitiveComposer


@pytest.fixture
def composer():
    return CognitiveComposer()


# ---------------------------------------------------------------------------
# Memory Intelligence — recall, persist, consolidate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description,classification",
    [
        (
            "recall prior decision",
            {
                "discipline": "architecture",
                "task_type": "research",
                "archetype": "researcher",
                "mode": "reflective",
                "complexity": "moderate",
                "description": "What did we decide about the routing approach last quarter? Recall the prior decision and its rationale.",
            },
        ),
        (
            "consolidate across sessions",
            {
                "discipline": "api_design",
                "task_type": "analyze",
                "archetype": "analyst",
                "mode": "reflective",
                "complexity": "moderate",
                "description": "Consolidate our recent decisions about the API contract across sessions",
            },
        ),
        (
            "persist pattern",
            {
                "discipline": "code_conventions",
                "task_type": "explain",
                "archetype": "researcher",
                "mode": "exploratory",
                "complexity": "moderate",
                "description": "Remember the pattern we used for the auth flow and persist it for next session",
            },
        ),
    ],
)
def test_memory_intelligence_self_nominates(composer, description, classification):
    selected = composer._select_meta_skills_dynamic(classification)
    assert "memory_intelligence" in selected, f"[{description}] memory should self-nominate; got {selected}"


# ---------------------------------------------------------------------------
# Gap Intelligence — coverage mapping, blind spots, what's missing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description,classification",
    [
        (
            "deployment coverage gaps",
            {
                "discipline": "deployment",
                "task_type": "review",
                "archetype": "sentinel",
                "mode": "reflective",
                "complexity": "complex",
                "description": "Audit the deployment pipeline for coverage gaps and blind spots",
            },
        ),
        (
            "testing strategy gaps",
            {
                "discipline": "testing",
                "task_type": "analyze",
                "archetype": "analyst",
                "mode": "deliberative",
                "complexity": "moderate",
                "description": "What's missing in our testing strategy? Find the blind spots and uncovered cases.",
            },
        ),
        (
            "security blind spots",
            {
                "discipline": "security",
                "task_type": "review",
                "archetype": "sentinel",
                "mode": "reflective",
                "complexity": "complex",
                "description": "Find the blind spots in our security model — what are we missing?",
            },
        ),
    ],
)
def test_gap_intelligence_self_nominates(composer, description, classification):
    selected = composer._select_meta_skills_dynamic(classification)
    assert "gap_intelligence" in selected, f"[{description}] gap should self-nominate; got {selected}"


# ---------------------------------------------------------------------------
# Coordination Intelligence — multi-agent, handoffs, conflict anticipation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description,classification",
    [
        (
            "parallel agents",
            {
                "discipline": "architecture",
                "task_type": "plan",
                "archetype": "executor",
                "mode": "procedural",
                "complexity": "complex",
                "description": "Split this refactor across 3 parallel agents and coordinate handoffs at merge points",
            },
        ),
        (
            "team migration coordination",
            {
                "discipline": "deployment",
                "task_type": "plan",
                "archetype": "executor",
                "mode": "deliberative",
                "complexity": "complex",
                "description": "Coordinate the team migration of the auth service — multi-agent, parallel streams, ownership boundaries",
            },
        ),
        (
            "handoff between teams",
            {
                "discipline": "integration",
                "task_type": "plan",
                "archetype": "advisor",
                "mode": "procedural",
                "complexity": "moderate",
                "description": "Set up handoff between the design team and engineering, with clear conflict anticipation",
            },
        ),
    ],
)
def test_coordination_intelligence_self_nominates(composer, description, classification):
    selected = composer._select_meta_skills_dynamic(classification)
    assert "coordination_intelligence" in selected, f"[{description}] coordination should self-nominate; got {selected}"


# ---------------------------------------------------------------------------
# Tool Intelligence — tool selection, chain composition, fallback strategy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description,classification",
    [
        (
            "data pipeline tool chain",
            {
                "discipline": "data",
                "task_type": "implement",
                "archetype": "executor",
                "mode": "procedural",
                "complexity": "moderate",
                "description": "Which tools should we use for the data pipeline? Compare options and pick a tool chain.",
            },
        ),
        (
            "websocket library choice",
            {
                "discipline": "integration",
                "task_type": "implement",
                "archetype": "executor",
                "mode": "procedural",
                "complexity": "simple",
                "description": "What's the best library for the WebSocket layer? Need fallback strategy too.",
            },
        ),
        (
            "Pandas vs Polars",
            {
                "discipline": "api_design",
                "task_type": "design",
                "archetype": "executor",
                "mode": "procedural",
                "complexity": "moderate",
                "description": "Choose between Pandas and Polars for this task — which tool fits best?",
            },
        ),
    ],
)
def test_tool_intelligence_self_nominates(composer, description, classification):
    selected = composer._select_meta_skills_dynamic(classification)
    assert "tool_intelligence" in selected, f"[{description}] tool should self-nominate; got {selected}"


# ---------------------------------------------------------------------------
# Precision: light-coverage skills should NOT fire on unrelated tasks
# ---------------------------------------------------------------------------


def test_memory_does_not_fire_on_fresh_build(composer):
    """A 'build this new feature from scratch' task shouldn't fire memory_intelligence —
    there's no recall happening."""
    selected = composer._select_meta_skills_dynamic(
        {
            "discipline": "architecture",
            "task_type": "build",
            "archetype": "creator",
            "mode": "deliberative",
            "complexity": "moderate",
            "description": "Build a new function that computes prime numbers from scratch",
        }
    )
    assert "memory_intelligence" not in selected, f"memory should not fire on fresh build; got {selected}"


def test_coordination_does_not_fire_on_simple_single_agent_task(composer):
    """A simple solo coding task shouldn't fire coordination_intelligence."""
    selected = composer._select_meta_skills_dynamic(
        {
            "discipline": "code_conventions",
            "task_type": "refactor",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
            "description": "Rename this variable from x to user_count",
        }
    )
    assert "coordination_intelligence" not in selected, (
        f"coordination should not fire on solo simple task; got {selected}"
    )
