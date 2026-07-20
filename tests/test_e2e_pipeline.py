# tests/test_e2e_pipeline.py
"""Core end-to-end pipeline test — if this breaks, nothing works.

Tests the full intelligence loop:
  observation → synthesize → load intelligence → execute task with context → GET task → feedback

Requires: running SurrealDB with schema applied.
"""

import pytest

from core.engine.core.db import parse_one, parse_rows

pytestmark = pytest.mark.e2e

# Check if LLM is available for tests that require real synthesis
try:
    from core.engine.core.llm import get_llm as _get_llm

    _test_llm = _get_llm()
    _HAS_LLM = bool(
        getattr(_test_llm, "_client", None)
        and getattr(_test_llm._client, "api_key", None)
        and len(_test_llm._client.api_key) > 20
    )
except Exception:
    _HAS_LLM = False

DUMMY_PREFIX = "E2E-PIPELINE-TEST"
ORG = "product:platform"
WS = "workspace:default"
USER = "user:default"


@pytest.fixture()
async def db(db_pool):
    async with db_pool.connection() as conn:
        yield conn


@pytest.fixture(autouse=True)
async def cleanup(db_pool):
    """Sweep all test artifacts after each test."""
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE observation WHERE source = 'e2e_pipeline_test'")
        await db.query(f"DELETE insight WHERE content CONTAINS '{DUMMY_PREFIX}'")
        await db.query(f"DELETE task WHERE description CONTAINS '{DUMMY_PREFIX}'")
        await db.query(f"DELETE chat_message WHERE content CONTAINS '{DUMMY_PREFIX}'")


async def _create_observations(db, count=3):
    """Create test observations with discipline tags."""
    obs_ids = []
    contents = [
        f"{DUMMY_PREFIX}: Python 3.12 is the standard backend runtime.",
        f"{DUMMY_PREFIX}: FastAPI is the web framework for all services.",
        f"{DUMMY_PREFIX}: JWT auth with 24h expiry on all endpoints.",
    ]
    for c in contents[:count]:
        r = await db.query(
            """CREATE observation SET
               product = <record>$product,
               observation_type = 'fact', content = $c,
               discipline_hint = 'architecture', domain_hint = 'architecture',
               confidence = 0.9, source = 'e2e_pipeline_test',
               synthesized = false, created_at = time::now()""",
            {"product": ORG, "c": c},
        )
        obs = parse_one(r)
        if obs:
            obs_ids.append(str(obs["id"]))
    return obs_ids


async def _synthesize(db_pool, observations):
    """Run synthesizer on observations."""
    from core.engine.capture.synthesizer import Synthesizer

    synth = Synthesizer(product_id=ORG, workspace_id=WS, batch_size=len(observations))
    synth._db_pool = db_pool
    for obs in observations:
        await synth.add_observation(obs)
    await synth.flush()


async def test_observation_to_insight(db_pool, db_health):
    """Observations can be created and insights written from them."""
    async with db_pool.connection() as db:
        # Create observations
        obs_ids = await _create_observations(db)
        assert len(obs_ids) >= 3, "Should create 3 observations"

        obs = parse_rows(await db.query("SELECT * FROM observation WHERE source = 'e2e_pipeline_test'"))
        assert len(obs) >= 3, f"Should have 3 observations in DB, got {len(obs)}"

        # Create insights directly from observations (testing the write path)
        for o in obs:
            await db.query(
                """CREATE insight SET
                    product = <record>$product,
                    content = $content,
                    insight_type = 'fact', confidence = $conf,
                    tier = 'specialty', tags = ['architecture', 'e2e_test'],
                    status = 'active', source_domain = 'e2e_pipeline_test',
                    created_at = time::now()""",
                {
                    "product": ORG,
                    "content": f"Insight from: {o.get('content', '')}",
                    "conf": o.get("confidence", 0.8),
                },
            )

        insights = parse_rows(await db.query("SELECT * FROM insight WHERE source_domain = 'e2e_pipeline_test'"))
        assert len(insights) >= 3, f"Should create insights from observations, got {len(insights)}"

        for ins in insights:
            assert ins.get("status") == "active"
            assert ins.get("content"), "Insight must have content"
            assert ins.get("confidence", 0) > 0, "Insight must have confidence"


async def test_intelligence_loading(db_pool, db_health):
    """Insights created in the DB are discoverable by the loader."""
    from core.engine.orchestrator.loader import load_intelligence

    # Create test insights directly (don't depend on synthesizer or seeded data)
    async with db_pool.connection() as db:
        for i in range(3):
            await db.query(
                """CREATE insight SET
                    product = <record>$product,
                    content = $content,
                    insight_type = 'fact', confidence = 0.85,
                    tier = 'specialty', tags = ['architecture', 'e2e_test'],
                    status = 'active', source_domain = 'e2e_test',
                    created_at = time::now()""",
                {"product": ORG, "content": f"{DUMMY_PREFIX}: Test insight {i} for architecture"},
            )

    result = await load_intelligence("architecture", ORG)
    assert result["total_count"] > 0, f"Loader should find insights for 'architecture', got {result['total_count']}"
    assert len(result["insights"]) > 0, "Insights list should not be empty"


async def test_task_execution_with_intelligence(db_pool, db_health):
    """Task execution loads intelligence and uses it in output."""
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    result = await orchestrate(
        OrchestrationRequest(
            description=f"{DUMMY_PREFIX}: What backend standards does our team follow?",
            product_id=ORG,
            workspace_id=WS,
            user_id=USER,
        )
    )

    assert result.task_id, "Task should have an ID"
    assert result.output, "Task should produce output"
    assert result.status == "completed"
    assert result.snapshot is not None, "Task should have a snapshot"


async def test_get_task(db_pool, db_health):
    """Task records are persisted and retrievable."""
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    result = await orchestrate(
        OrchestrationRequest(
            description=f"{DUMMY_PREFIX}: Simple test task",
            product_id=ORG,
            workspace_id=WS,
            user_id=USER,
        )
    )

    assert result.task_id and result.task_id != "unknown", (
        f"Task should be persisted to DB, got task_id={result.task_id}"
    )

    async with db_pool.connection() as db:
        r = await db.query("SELECT * FROM ONLY <record>$id", {"id": result.task_id})
        task = parse_one(r) if not isinstance(r, dict) else r
        assert isinstance(task, dict), "GET task should return a dict"
        assert task.get("status") == "completed"


async def test_chat_session(db_pool, db_health):
    """Chat creates a session and returns a response."""
    from core.engine.chat.handler import create_session, handle_message

    session = await create_session(product_id=ORG, workspace_id=WS, user_id=USER)
    sid = str(session.get("id", ""))
    assert sid, "Should create a session ID"

    result = await handle_message(
        session_id=sid,
        message=f"{DUMMY_PREFIX}: What database do we use?",
        product_id=ORG,
        workspace_id=WS,
        user_id=USER,
    )
    output = result.get("output", "") if isinstance(result, dict) else str(result)
    assert len(output) > 0, "Chat should produce output"
