# tests/test_skill_executor.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.skills.models import Job, Phase, Skill, Slot


def _make_skill(slug, phases=None, jobs=None):
    return Skill(
        slug=slug,
        name=slug.title(),
        description="test skill",
        phases=phases or [],
        jobs=jobs or [],
        activation_signals=[slug],
    )


def _solo_phase(name, archetype="executor", mode="reactive"):
    return Phase(
        name=name,
        pattern="solo",
        slots=[Slot(archetype=archetype, mode=mode)],
    )


@pytest.mark.asyncio
async def test_single_phase_execution():
    """Single-phase skill returns the LLM output."""
    from core.engine.skills.executor import execute_skill

    skill = _make_skill("brainstorm", phases=[_solo_phase("ideate", "creator", "exploratory")])

    with (
        patch("core.engine.skills.executor.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.skills.executor.llm") as mock_llm,
        patch("core.engine.skills.executor.pool") as mock_pool,
    ):
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.complete = AsyncMock(return_value="Here are 5 ideas...")
        mock_pool.connection.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(query=AsyncMock(return_value=[]))
        )
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await execute_skill(skill, "brainstorm ideas", "product:test", "ws:test", "user:test")

    assert result["output"] == "Here are 5 ideas..."
    assert result["phases_completed"] == 1
    assert result["skill_slug"] == "brainstorm"
    assert len(result["phase_results"]) == 1
    assert result["phase_results"][0]["phase"] == "ideate"


@pytest.mark.asyncio
async def test_legacy_jobs_migrated_to_phases():
    """Skills with old-style jobs are automatically migrated to phases."""
    from core.engine.skills.executor import execute_skill

    skill = _make_skill(
        "brainstorm",
        jobs=[Job(name="ideate", archetype="creator", mode="exploratory")],
    )

    assert len(skill.phases) == 1
    assert skill.phases[0].name == "ideate"
    assert skill.phases[0].pattern == "solo"
    assert skill.phases[0].slots[0].archetype == "creator"

    with (
        patch("core.engine.skills.executor.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.skills.executor.llm") as mock_llm,
        patch("core.engine.skills.executor.pool") as mock_pool,
    ):
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.complete = AsyncMock(return_value="legacy output")
        mock_pool.connection.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(query=AsyncMock(return_value=[]))
        )
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await execute_skill(skill, "test task", "product:test", "ws:test", "user:test")

    assert result["output"] == "legacy output"
    assert result["phases_completed"] == 1


@pytest.mark.asyncio
async def test_multi_phase_chains_context():
    """Multi-phase skill passes prior phase output as context to next phase."""
    from core.engine.skills.executor import execute_skill

    skill = _make_skill(
        "deep-research",
        phases=[
            _solo_phase("gather", "researcher", "exploratory"),
            _solo_phase("analyze", "analyst", "deliberative"),
        ],
    )

    call_count = 0

    async def mock_complete(prompt, model=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "Gathered data: X, Y, Z"
        else:
            assert "Gathered data: X, Y, Z" in prompt
            return "Analysis: X is most significant"

    with (
        patch("core.engine.skills.executor.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.skills.executor.llm") as mock_llm,
        patch("core.engine.skills.executor.pool") as mock_pool,
    ):
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.complete = mock_complete
        mock_pool.connection.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(query=AsyncMock(return_value=[]))
        )
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await execute_skill(skill, "research topic X", "product:test", "ws:test", "user:test")

    assert result["phases_completed"] == 2
    assert result["output"] == "Analysis: X is most significant"
    assert call_count == 2


@pytest.mark.asyncio
async def test_phase_failure_surfaces_error():
    """If a phase slot fails with an exception, execution stops gracefully."""
    from core.engine.skills.executor import execute_skill

    skill = _make_skill(
        "two-phase",
        phases=[
            _solo_phase("phase1", "creator", "reactive"),
            _solo_phase("phase2", "analyst", "deliberative"),
        ],
    )

    with (
        patch("core.engine.skills.executor.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.skills.executor.llm") as mock_llm,
        patch("core.engine.skills.executor.pool") as mock_pool,
    ):
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("LLM error"))
        mock_pool.connection.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(query=AsyncMock(return_value=[]))
        )
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await execute_skill(skill, "test task", "product:test", "ws:test", "user:test")

    assert result["phases_completed"] == 0
    assert "error" in result["phase_results"][0]["slot_results"][0]


@pytest.mark.asyncio
async def test_parallel_phase_runs_all_slots():
    """Parallel phase runs all slots concurrently and aggregates."""
    from core.engine.skills.executor import execute_skill

    skill = _make_skill(
        "multi-view",
        phases=[
            Phase(
                name="analyze",
                pattern="parallel",
                slots=[
                    Slot(archetype="analyst", mode="deliberative"),
                    Slot(archetype="sentinel", mode="reflective"),
                ],
                aggregation="merge",
            )
        ],
    )

    call_count = 0

    async def mock_complete(prompt, model=None):
        nonlocal call_count
        call_count += 1
        return f"output-{call_count}"

    with (
        patch("core.engine.skills.executor.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.skills.executor.llm") as mock_llm,
        patch("core.engine.skills.executor.pool") as mock_pool,
    ):
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.complete = mock_complete
        mock_pool.connection.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(query=AsyncMock(return_value=[]))
        )
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await execute_skill(skill, "analyze this", "product:test", "ws:test", "user:test")

    assert call_count == 2  # both slots ran
    assert result["phases_completed"] == 1


@pytest.mark.asyncio
async def test_slot_uses_own_archetype_mode():
    """Each slot should inject its own archetype/mode instructions."""
    from core.engine.skills.executor import execute_skill

    skill = _make_skill(
        "mixed",
        phases=[
            _solo_phase("research", "researcher", "exploratory"),
            _solo_phase("create", "creator", "deliberative"),
        ],
    )

    prompts_seen = []

    async def capture_prompt(prompt, model=None):
        prompts_seen.append(prompt)
        return "output"

    with (
        patch("core.engine.skills.executor.load_intelligence", new_callable=AsyncMock) as mock_load,
        patch("core.engine.skills.executor.llm") as mock_llm,
        patch("core.engine.skills.executor.pool") as mock_pool,
    ):
        mock_load.return_value = {"insights": [], "total_count": 0}
        mock_llm.complete = capture_prompt
        mock_pool.connection.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(query=AsyncMock(return_value=[]))
        )
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await execute_skill(skill, "test", "product:test", "ws:test", "user:test")

    assert "mapping territory" in prompts_seen[0].lower() or "cast wide" in prompts_seen[0].lower()
    assert (
        "building something that doesn't exist" in prompts_seen[1].lower()
        or "worth building" in prompts_seen[1].lower()
    )


@pytest.mark.asyncio
async def test_classification_discipline_used_in_intelligence_load():
    """When classification is provided, its discipline reaches load_intelligence."""
    from core.engine.skills.executor import execute_skill

    skill = _make_skill("sec-audit", phases=[_solo_phase("scan", "sentinel", "reflective")])

    captured_calls = []

    async def mock_load(discipline, product_id, **kwargs):
        captured_calls.append({"discipline": discipline, **kwargs})
        return {"insights": [], "total_count": 0}

    with (
        patch("core.engine.skills.executor.load_intelligence", side_effect=mock_load),
        patch("core.engine.skills.executor.llm") as mock_llm,
        patch("core.engine.skills.executor.pool") as mock_pool,
    ):
        mock_llm.complete = AsyncMock(return_value="output")
        mock_pool.connection.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(query=AsyncMock(return_value=[]))
        )
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await execute_skill(
            skill,
            "audit security",
            "product:test",
            "ws:test",
            "user:test",
            classification={"discipline": "security", "discipline_confidence": 0.9},
        )

    assert captured_calls, "load_intelligence was never called"
    assert captured_calls[0]["discipline"] == "security"


@pytest.mark.asyncio
async def test_low_confidence_loads_adjacent_disciplines():
    """When discipline_confidence is below threshold, adjacent disciplines are loaded."""
    from core.engine.skills.executor import execute_skill

    skill = _make_skill("scan", phases=[_solo_phase("check", "sentinel", "reflective")])

    captured_calls = []

    async def mock_load(discipline, product_id, **kwargs):
        captured_calls.append({"discipline": discipline, "adjacent": kwargs.get("adjacent_disciplines")})
        return {"insights": [], "total_count": 0}

    with (
        patch("core.engine.skills.executor.load_intelligence", side_effect=mock_load),
        patch("core.engine.skills.executor.llm") as mock_llm,
        patch("core.engine.skills.executor.pool") as mock_pool,
    ):
        mock_llm.complete = AsyncMock(return_value="output")
        mock_pool.connection.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(query=AsyncMock(return_value=[]))
        )
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await execute_skill(
            skill,
            "check security",
            "product:test",
            "ws:test",
            "user:test",
            classification={"discipline": "security", "discipline_confidence": 0.4},
        )

    assert captured_calls, "load_intelligence was never called"
    assert captured_calls[0]["discipline"] == "security"
    assert captured_calls[0]["adjacent"] is not None
    assert len(captured_calls[0]["adjacent"]) > 0


@pytest.mark.asyncio
async def test_skill_discipline_used_when_no_classification():
    """Skill's own discipline is used when no classification is provided."""
    from core.engine.skills.models import Skill

    skill = Skill(
        slug="api-design",
        name="API Design",
        description="design APIs",
        discipline="api_design",
        phases=[_solo_phase("design", "creator", "deliberative")],
        activation_signals=["api"],
    )

    captured_calls = []

    async def mock_load(discipline, product_id, **kwargs):
        captured_calls.append(discipline)
        return {"insights": [], "total_count": 0}

    with (
        patch("core.engine.skills.executor.load_intelligence", side_effect=mock_load),
        patch("core.engine.skills.executor.llm") as mock_llm,
        patch("core.engine.skills.executor.pool") as mock_pool,
    ):
        mock_llm.complete = AsyncMock(return_value="output")
        mock_pool.connection.return_value.__aenter__ = AsyncMock(
            return_value=AsyncMock(query=AsyncMock(return_value=[]))
        )
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        from core.engine.skills.executor import execute_skill

        await execute_skill(skill, "design REST API", "product:test", "ws:test", "user:test")

    assert captured_calls[0] == "api_design"
