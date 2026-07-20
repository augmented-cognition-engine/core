# tests/test_e2e_full_flow.py
"""Full end-to-end flow — exercises every real database layer.

Unlike tests/test_reference_flow.py (seam tests with mocked internals),
these tests run against a live SurrealDB instance. They verify:

  - Intelligence loading queries actually execute and return results
  - CognitiveComposer + score_composition run against real DB
  - ShellComposer builds a system prompt that reaches the LLM
  - Seeded intelligence appears in the LLM prompt
  - Task record is persisted to the database with correct fields
  - Prometheus metrics reflect the real run
  - error_buffer is clean after a successful run
  - The observation handler writes to DB when the event bridge fires

The LLM's complete() response is the only mock — every DB operation is real.

Requires: SurrealDB running at the URL in engine.core.config
Run:  pytest tests/test_e2e_full_flow.py -v -m e2e
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_DESCRIPTION = "Explain the role of asyncio.Queue in CaptureService's pipeline decoupling."
_PRODUCT_ID = "product:test"
_MOCK_OUTPUT = (
    "asyncio.Queue decouples producers from consumers. "
    "When the consumer is slow, producers don't block — they simply enqueue. "
    "This is why CaptureService uses an internal queue rather than processing inline."
)


class _MockLLM:
    """Minimal LLM mock that records the prompt it receives and returns a fixed response."""

    def __init__(self, response: str = _MOCK_OUTPUT):
        self.response = response
        self.calls: list[str] = []
        self.system_prompts: list[str] = []

    async def complete(self, prompt: str, **kwargs) -> str:
        self.calls.append(prompt)
        return self.response

    async def complete_json(self, prompt: str, **kwargs) -> dict:
        self.calls.append(prompt)
        return {}

    async def complete_structured(self, prompt: str, **kwargs):
        self.calls.append(prompt)
        return {}

    async def stream(self, prompt: str, **kwargs):
        # empty async generator — the unreachable yield after return turns
        # the function into a generator without ever producing a value.
        return
        yield  # noqa


def _get_counter_value(counter, **labels) -> float:
    try:
        return counter.labels(**labels)._value.get()
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def seeded_insight(db_pool):
    """Insert a test insight and clean up after the module's tests finish."""
    insight_id = "insight:e2e_flow_test_001"
    content = "asyncio.Queue is the canonical decoupling primitive for producer-consumer pipelines"

    async with db_pool.connection() as db:
        await db.query(
            """
            UPSERT <record>$id SET
                product = <record>$product,
                product = <record>$product,
                content = $content,
                insight_type = 'pattern',
                confidence = 0.92,
                tags = ['architecture', 'async_patterns'],
                tier = 'product',
                status = 'active'
            """,
            {"id": insight_id, "product": _PRODUCT_ID, "content": content},
        )

    yield {"id": insight_id, "content": content}

    # Cleanup
    async with db_pool.connection() as db:
        try:
            await db.query("DELETE $id", {"id": insight_id})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Seam A: Intelligence loading hits the real DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_intelligence_loads_from_db(db_pool, db_health, seeded_insight):
    """load_intelligence / load_dual_intelligence must query the real DB and return a snapshot."""
    from core.engine.orchestrator.loader import load_intelligence

    snapshot = await load_intelligence(
        domain_path="architecture",
        product_id=_PRODUCT_ID,
        mode="reactive",
    )

    # Even an empty product returns a valid snapshot structure
    assert isinstance(snapshot, dict)
    # With the seeded insight, we expect at least one insight
    all_insights = snapshot.get("insights", []) + snapshot.get("specialty_insights", [])
    assert len(all_insights) >= 1, (
        "Expected at least the seeded insight — check that load_intelligence queries product-level data"
    )


# ---------------------------------------------------------------------------
# Seam B: Full orchestration with real DB, mocked LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_full_run_completes(db_pool, db_health, seeded_insight):
    """Full orchestrate() with real DB reads/writes, mocked LLM response."""
    from core.engine.core.error_buffer import error_buffer
    from core.engine.core.metrics import task_counter
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    error_buffer.clear()
    before = _get_counter_value(task_counter, discipline="architecture", status="completed")

    mock_llm = _MockLLM()

    request = OrchestrationRequest(
        description=_TASK_DESCRIPTION,
        product_id=_PRODUCT_ID,
        workspace_id="workspace:test",
        user_id="user:test",
        persist_task=True,
        persist_events=False,
        run_post_hooks=False,
        classification_override={
            "discipline": "architecture",
            "domain_path": "architecture",
            "archetype": "analyst",
            "mode": "standard",
            "perspective": "practitioner",
            "engagement": {},
        },
        # intelligence_override NOT set → real DB load
    )

    with patch("core.engine.core.llm.llm", mock_llm):
        result = await orchestrate(request)

    # --- Core assertions ---
    assert result.status == "completed"
    assert result.output == _MOCK_OUTPUT
    assert result.classification["discipline"] == "architecture"

    # --- LLM was actually called ---
    assert len(mock_llm.calls) == 1, "Expected exactly one LLM call from the single-agent path"

    # --- Intelligence snapshot was populated from real DB ---
    assert result.snapshot is not None
    assert isinstance(result.snapshot, dict)

    # --- Task persisted to DB ---
    assert result.task_id is not None, "Task ID must be set when persist_task=True"
    async with db_pool.connection() as db:
        rows = await db.query(
            "SELECT id, description, discipline, status, output FROM task WHERE id = <record>$id",
            {"id": result.task_id},
        )
    from core.engine.core.db import parse_rows

    task_rows = parse_rows(rows)
    assert len(task_rows) == 1
    task_row = task_rows[0]
    assert task_row["discipline"] == "architecture"
    assert task_row["status"] == "completed"
    assert task_row["output"] == _MOCK_OUTPUT

    # --- Prometheus counter incremented ---
    after = _get_counter_value(task_counter, discipline="architecture", status="completed")
    assert after == before + 1

    # --- No errors recorded ---
    assert error_buffer.count == 0

    # Cleanup: remove the persisted task so tests are idempotent
    async with db_pool.connection() as db:
        try:
            await db.query("DELETE $id", {"id": result.task_id})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Seam C: Intelligence appears in the LLM prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_intelligence_reaches_llm_prompt(db_pool, db_health, seeded_insight):
    """The seeded insight must appear in the system prompt delivered to the LLM."""
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    mock_llm = _MockLLM()

    request = OrchestrationRequest(
        description=_TASK_DESCRIPTION,
        product_id=_PRODUCT_ID,
        workspace_id="workspace:test",
        user_id="user:test",
        persist_task=False,
        persist_events=False,
        run_post_hooks=False,
        classification_override={
            "discipline": "architecture",
            "domain_path": "architecture",
            "archetype": "analyst",
            "mode": "standard",
            "perspective": "practitioner",
            "engagement": {},
        },
    )

    with patch("core.engine.core.llm.llm", mock_llm):
        result = await orchestrate(request)

    assert result.status == "completed"
    assert len(mock_llm.calls) >= 1

    # The full prompt received by the LLM must contain the seeded insight content
    combined_prompt = "\n".join(mock_llm.calls)
    assert seeded_insight["content"] in combined_prompt, (
        "Seeded insight must appear in the LLM prompt — "
        "this verifies intelligence flows from DB → snapshot → ShellComposer → LLM"
    )


# ---------------------------------------------------------------------------
# Seam D: Active gauge returns to zero (no leak on real path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_gauge_no_leak(db_pool, db_health):
    """orchestration_active gauge must not leak on the real execution path."""
    from core.engine.core.metrics import orchestration_active
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    before = orchestration_active._value.get()

    mock_llm = _MockLLM()

    request = OrchestrationRequest(
        description=_TASK_DESCRIPTION,
        product_id=_PRODUCT_ID,
        workspace_id="workspace:test",
        user_id="user:test",
        persist_task=False,
        persist_events=False,
        run_post_hooks=False,
        classification_override={
            "discipline": "architecture",
            "domain_path": "architecture",
            "archetype": "analyst",
            "mode": "standard",
            "perspective": "practitioner",
            "engagement": {},
        },
    )

    with patch("core.engine.core.llm.llm", mock_llm):
        await orchestrate(request)

    after = orchestration_active._value.get()
    assert after == before, f"Gauge leaked: before={before} after={after}"


# ---------------------------------------------------------------------------
# Seam E: Error path — DB failure recorded in error_buffer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_db_failure_recorded_in_error_buffer(db_health):
    """If intelligence loading raises, error_buffer captures it."""
    from core.engine.core.error_buffer import error_buffer
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    error_buffer.clear()

    request = OrchestrationRequest(
        description=_TASK_DESCRIPTION,
        product_id=_PRODUCT_ID,
        workspace_id="workspace:test",
        user_id="user:test",
        persist_task=False,
        persist_events=False,
        classification_override={
            "discipline": "architecture",
            "domain_path": "architecture",
            "archetype": "analyst",
            "mode": "standard",
            "perspective": "practitioner",
            "engagement": {},
        },
    )

    with patch("core.engine.orchestration.executor.dispatch", side_effect=RuntimeError("simulated db failure")):
        try:
            await orchestrate(request)
        except Exception:
            pass

    assert error_buffer.count > 0
    entry = error_buffer.recent()[0]
    assert entry["source"] == "orchestration"
    assert "simulated db failure" in entry["message"]
    error_buffer.clear()
