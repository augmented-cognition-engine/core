import asyncio

from core.engine.core.tokens import TokenAccumulator, clear_accumulator, get_accumulator, set_accumulator


def test_record_and_totals():
    acc = TokenAccumulator()
    acc.record("complete", 100, 50, purpose="classifier")
    acc.record("complete_structured", 200, 150, purpose="spin_1")
    assert acc.total_input() == 300
    assert acc.total_output() == 200
    assert acc.total() == 500


def test_empty_accumulator():
    acc = TokenAccumulator()
    assert acc.total() == 0
    assert acc.total_input() == 0
    assert acc.total_output() == 0
    s = acc.summary()
    assert s["calls"] == []
    assert s["input_tokens"] == 0
    assert s["output_tokens"] == 0
    assert s["total_tokens"] == 0
    assert s["cache_read_input_tokens"] == 0
    assert s["cache_creation_input_tokens"] == 0
    # Phase 1 additions: cost_usd and stages are present
    assert s["cost_usd"] == 0.0
    assert s["providers"] == []
    assert s["models"] == []
    assert s["stages"] == {}


def test_summary_structure():
    acc = TokenAccumulator()
    acc.record("complete", 100, 50, purpose="test")
    s = acc.summary()
    assert s["input_tokens"] == 100
    assert s["output_tokens"] == 50
    assert s["total_tokens"] == 150
    assert len(s["calls"]) == 1
    assert s["calls"][0]["method"] == "complete"
    assert s["calls"][0]["purpose"] == "test"


def test_explicit_local_cost_and_route_override_default_rates():
    acc = TokenAccumulator()
    acc.record(
        "complete",
        100,
        50,
        provider="OllamaProvider",
        model="qwen3:4b",
        cost_usd=0.0,
    )
    summary = acc.summary()
    assert summary["cost_usd"] == 0.0
    assert summary["providers"] == ["OllamaProvider"]
    assert summary["models"] == ["qwen3:4b"]


def test_contextvars_isolation():
    """Two concurrent tasks get isolated accumulators."""
    results = {}

    async def task_a():
        acc = TokenAccumulator()
        set_accumulator(acc)
        acc.record("complete", 100, 50)
        await asyncio.sleep(0.01)
        results["a"] = get_accumulator().total()

    async def task_b():
        acc = TokenAccumulator()
        set_accumulator(acc)
        acc.record("complete", 200, 100)
        await asyncio.sleep(0.01)
        results["b"] = get_accumulator().total()

    async def run():
        await asyncio.gather(task_a(), task_b())

    asyncio.run(run())
    assert results["a"] == 150
    assert results["b"] == 300


def test_gather_inherits_accumulator():
    """asyncio.gather propagates parent's ContextVar to child tasks (Python 3.12+)."""

    async def inner():
        parent_acc = TokenAccumulator()
        set_accumulator(parent_acc)
        parent_acc.record("complete", 100, 50, purpose="parent")

        async def child():
            acc = get_accumulator()
            assert acc is not None
            acc.record("complete", 200, 100, purpose="child")

        await asyncio.gather(child(), child())
        assert parent_acc.total() == 750  # 150 + 300 + 300

    asyncio.run(inner())


def test_clear_accumulator():
    acc = TokenAccumulator()
    set_accumulator(acc)
    assert get_accumulator() is acc
    clear_accumulator()
    assert get_accumulator() is None
