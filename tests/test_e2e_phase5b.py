# tests/test_e2e_phase5b.py
"""E2E integration tests for the ideas + playbooks pipeline."""

import pytest

pytestmark = pytest.mark.e2e
from unittest.mock import AsyncMock, patch

from core.engine.ideas.schemas import IdeaClassification, IncubationBrief, QualificationResult
from core.engine.ideas.state_machine import IdeaStateError


@pytest.mark.asyncio
async def test_e2e_idea_to_ready():
    """Full pipeline: capture → qualify (which invokes incubate inline) → ready.

    Updated for the inline-incubation contract: qualify's "ready" fast-path
    no longer transitions status directly; it runs incubate_idea so the brief
    lands before the idea surfaces as "ready for review." See qualify.py.
    """
    from core.engine.ideas.capture import capture_idea
    from core.engine.ideas.incubate import incubate_idea
    from core.engine.ideas.qualify import qualify_idea

    mock_class = IdeaClassification(
        domain_path="architecture",
        type="feature",
        complexity="moderate",
        title="API caching",
        summary="Add caching to the API.",
    )
    mock_qual = QualificationResult(status="ready", questions=[])
    mock_brief = IncubationBrief(
        what="API cache",
        why="Performance",
        what_we_know="Redis available",
        open_questions=[],
        approach="Redis + TTL",
        effort="1w",
        risks=["Stale data"],
        first_step="Define keys",
    )

    with (
        patch("core.engine.ideas.capture.llm") as cap_llm,
        patch("core.engine.ideas.capture.pool") as cap_pool,
        patch("core.engine.ideas.qualify.llm") as qual_llm,
        patch("core.engine.ideas.qualify.pool") as qual_pool,
        patch("core.engine.ideas.incubate.llm") as inc_llm,
        patch("core.engine.ideas.incubate.pool") as inc_pool,
    ):
        # Capture
        cap_llm.complete_structured = AsyncMock(return_value=mock_class)
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "idea:e2e1",
                        "status": "captured",
                        "title": "API caching",
                        "raw_input": "Add caching",
                        "classification": mock_class.model_dump(),
                    }
                ]
            ]
        )
        cap_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        cap_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        idea = await capture_idea("Add caching to the API", "user:ed", "product:default")
        assert idea["status"] == "captured"

        # Set up incubation mocks BEFORE qualify (qualify now invokes incubate inline).
        inc_llm.complete_structured = AsyncMock(return_value=mock_brief)
        inc_llm.complete_json = AsyncMock(return_value=[])
        inc_conn = AsyncMock()
        inc_conn.query = AsyncMock(return_value=[[]])
        inc_pool.connection.return_value.__aenter__ = AsyncMock(return_value=inc_conn)
        inc_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        # Qualify ("ready" fast-path) — invokes incubate inline.
        qual_llm.complete_structured = AsyncMock(return_value=mock_qual)
        qual_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        qual_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        qual_result = await qualify_idea(idea, "product:default")
        # QualificationResult(status="ready") + 5+ brief fields → reaches ready.
        assert qual_result["status"] == "ready"
        assert qual_result.get("incubation_deferred") is None  # no deferral

        # Sanity: separate incubate call on an 'open' idea still respects the
        # "open ideas don't auto-promote" rule (covered for completeness).
        idea["status"] = "open"
        inc_result = await incubate_idea(idea, "product:default")
        assert inc_result["status"] == "open"
        assert inc_result["brief"]["what"] == "API cache"


@pytest.mark.asyncio
async def test_e2e_idea_with_qualification():
    """Pipeline with qualifying questions: capture → qualify → answer → incubating."""
    from core.engine.ideas.qualify import answer_qualifying_questions, qualify_idea

    mock_qual = QualificationResult(
        status="needs_questions",
        questions=["For how many brands?", "Which brands?"],
    )

    with patch("core.engine.ideas.qualify.llm") as mock_llm, patch("core.engine.ideas.qualify.pool") as mock_pool:
        mock_llm.complete_structured = AsyncMock(return_value=mock_qual)
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await qualify_idea(
            {"id": "idea:q1", "raw_input": "Multi-brand themes", "status": "captured"},
            "product:default",
        )
        # QualificationResult(status="needs_questions") → state machine transitions captured → qualifying
        assert result["status"] == "qualifying"
        assert len(result["questions"]) == 2

        # Answer questions
        call_count = 0

        async def answer_side_effect(query_str, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    [
                        {
                            "id": "idea:q1",
                            "status": "open",
                            "qualifying_qs": [
                                {"q": "For how many brands?", "a": None},
                                {"q": "Which brands?", "a": None},
                            ],
                        }
                    ]
                ]
            return [[{"id": "idea:q1", "status": "ready"}]]

        mock_conn.query = AsyncMock(side_effect=answer_side_effect)

        answer_result = await answer_qualifying_questions("idea:q1", ["3 brands", "Acme, Bolt, Crest"])
        assert answer_result["status"] == "ready"


@pytest.mark.asyncio
async def test_e2e_playbook_round_trip():
    """Create playbook → instantiate with variables → initiative created."""
    from core.engine.templates.instantiate import instantiate_template

    playbook = {
        "id": "playbook:e2e",
        "name": "E2E Test Template",
        "description": "Test for {{project_name}}",
        "domain_path": "architecture",
        "variables": [{"name": "project_name", "type": "string", "prompt": "Project?"}],
        "milestones": [
            {
                "title": "M1: Setup {{project_name}}",
                "done_criteria": ["Project setup"],
                "work_items": [
                    {
                        "title": "Configure {{project_name}}",
                        "archetype": "executor",
                        "mode": "procedural",
                        "domain_path": "architecture",
                    },
                ],
            },
        ],
    }

    with patch("core.engine.templates.instantiate.pool") as mock_pool:
        mock_conn = AsyncMock()
        created = None

        async def track(query_str, params=None):
            nonlocal created
            if "CREATE initiative" in query_str:
                created = params
                return [[{"id": "initiative:e2e1", "source": "template"}]]
            return [[]]

        mock_conn.query = track
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await instantiate_template(
            playbook=playbook,
            variables={"project_name": "APOLLO"},
            user_id="user:ed",
            product_id="product:default",
        )

    assert created is not None
    assert "APOLLO" in created["milestones"][0]["title"]
    assert "{{project_name}}" not in created["milestones"][0]["title"]


@pytest.mark.asyncio
async def test_e2e_playbook_detection():
    """3 structurally similar completed initiatives trigger playbook suggestion."""
    from core.engine.templates.suggest import find_clusters

    def make_init(name):
        return {
            "id": f"initiative:{name}",
            "title": name,
            "domain_path": "architecture",
            "milestones_detail": [
                {
                    "title": "M1",
                    "work_items_detail": [
                        {"archetype": "researcher", "mode": "exploratory", "domain_path": "architecture"},
                    ],
                },
                {
                    "title": "M2",
                    "work_items_detail": [
                        {"archetype": "creator", "mode": "deliberative", "domain_path": "architecture"},
                        {"archetype": "analyst", "mode": "reactive", "domain_path": "testing"},
                    ],
                },
            ],
        }

    inits = [make_init("A"), make_init("B"), make_init("C")]
    clusters = find_clusters(inits)
    assert len(clusters) == 1
    assert len(clusters[0]) == 3


@pytest.mark.asyncio
async def test_e2e_skill_emergence():
    """5+ tasks with same pattern and high feedback trigger skill suggestion."""
    from core.engine.templates.emergence import detect_patterns

    tasks = [
        {
            "archetype": "creator",
            "mode": "deliberative",
            "domain_path": "ux",
            "description": f"Build component {i}",
            "feedback_human": "accepted",
            "status": "completed",
        }
        for i in range(6)
    ]
    suggestions = detect_patterns(tasks)
    assert len(suggestions) == 1
    assert suggestions[0]["task_count"] == 6


@pytest.mark.asyncio
async def test_e2e_state_machine_enforced():
    """State machine prevents invalid transitions."""
    from core.engine.ideas.activate import activate_idea

    # Can't activate a captured idea (must go through incubation first)
    with pytest.raises(IdeaStateError):
        await activate_idea(
            idea={"id": "idea:bad", "status": "captured", "title": "Bad"},
            user_id="user:ed",
            product_id="product:default",
        )
