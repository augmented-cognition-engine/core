# tests/test_synthesizer_cognify.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.capture.synthesizer import Synthesizer


def _synth():
    s = Synthesizer(product_id="product:test", workspace_id=None)
    s._db_pool = object()  # truthy; atomic_capture_write is patched
    return s


@pytest.mark.asyncio
async def test_write_insight_returns_record_with_id_content_embedding():
    s = _synth()
    with (
        patch(
            "core.engine.capture.synthesizer.atomic_capture_write",
            new=AsyncMock(return_value="insight:abc"),
        ),
        patch("core.engine.capture.synthesizer.get_embedder") as ge,
    ):
        ge.return_value.dimensions = 3
        ge.return_value.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        rec = await s._write_insight({"content": "X depends on Y", "insight_type": "fact"})
    assert rec is not None
    assert rec["id"] == "insight:abc"
    assert rec["content"] == "X depends on Y"
    assert rec["embedding"] == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_write_insight_returns_none_without_db():
    s = Synthesizer(product_id="product:test", workspace_id=None)
    s._db_pool = None
    assert await s._write_insight({"content": "x"}) is None


@pytest.mark.asyncio
async def test_write_insight_returns_none_for_consolidation_stub():
    s = _synth()
    assert await s._write_insight({"content": "Consolidated with insight:zzz — merged"}) is None


@pytest.mark.asyncio
async def test_write_new_insights_returns_records():
    s = _synth()
    s._write_insight = AsyncMock(side_effect=[{"id": "insight:1", "content": "a", "embedding": [1.0]}, None])
    written, failures, records = await s._write_new_insights(
        [{"content": "a"}, {"content": "Consolidated with insight:z — x"}], "", []
    )
    assert written == 2  # both calls succeeded (no exception); None just means no record surfaced
    assert failures == 0
    assert records == [{"id": "insight:1", "content": "a", "embedding": [1.0]}]


@pytest.mark.asyncio
async def test_candidate_finder_ranks_existing_by_cosine():
    s = _synth()
    existing = [
        {"id": "insight:far", "content": "unrelated", "embedding": [0.0, 1.0]},
        {"id": "insight:near", "content": "related", "embedding": [1.0, 0.0]},
        {"id": "insight:noemb", "content": "no embedding"},  # dropped (no embedding)
    ]
    finder = s._cognify_candidate_finder(existing)
    ranked = await finder({"id": "insight:new", "content": "x", "embedding": [0.9, 0.1]})
    assert [c["id"] for c in ranked] == ["insight:near", "insight:far"]


@pytest.mark.asyncio
async def test_candidate_finder_empty_when_new_has_no_embedding():
    s = _synth()
    finder = s._cognify_candidate_finder([{"id": "insight:a", "content": "a", "embedding": [1.0]}])
    assert await finder({"id": "insight:new", "content": "x"}) == []


@pytest.mark.asyncio
async def test_maybe_cognify_returns_none_when_disabled(monkeypatch):
    import core.engine.capture.synthesizer as syn

    monkeypatch.setattr(syn.settings, "cognify_enabled", False)
    s = _synth()
    task = s._maybe_cognify(
        [{"id": "insight:1", "content": "a", "embedding": [1.0]}],
        [{"id": "insight:2", "content": "b", "embedding": [1.0]}],
    )
    assert task is None


@pytest.mark.asyncio
async def test_maybe_cognify_runs_cognify_when_enabled(monkeypatch):
    import core.engine.capture.synthesizer as syn

    monkeypatch.setattr(syn.settings, "cognify_enabled", True)
    s = _synth()
    seen = {}

    async def fake_cognify(new_records, find_candidates, **kw):
        seen["records"] = new_records
        seen["candidates"] = await find_candidates(new_records[0])
        seen["kw"] = kw
        return 1

    monkeypatch.setattr(syn, "cognify", fake_cognify)
    task = s._maybe_cognify(
        [{"id": "insight:new", "content": "a", "embedding": [1.0, 0.0]}],
        [{"id": "insight:cand", "content": "b", "embedding": [1.0, 0.0]}],
    )
    assert task is not None
    result = await task
    assert result == 1
    assert seen["records"][0]["id"] == "insight:new"
    assert seen["candidates"][0]["id"] == "insight:cand"
    assert seen["kw"] == {"min_confidence": 0.6, "candidate_k": 8}


@pytest.mark.asyncio
async def test_maybe_cognify_none_when_no_records(monkeypatch):
    import core.engine.capture.synthesizer as syn

    monkeypatch.setattr(syn.settings, "cognify_enabled", True)
    s = _synth()
    assert s._maybe_cognify([], [{"id": "insight:c", "content": "b", "embedding": [1.0]}]) is None


@pytest.mark.asyncio
async def test_synthesize_fires_cognify_after_write(monkeypatch):
    import core.engine.capture.synthesizer as syn

    monkeypatch.setattr(syn.settings, "cognify_enabled", True)
    s = _synth()
    s._pending = [{"id": "obs:1", "content": "X depends on Y", "discipline_hint": "architecture"}]

    monkeypatch.setattr(
        s,
        "_load_existing_insights",
        AsyncMock(
            return_value=[
                {"id": "insight:cand", "content": "Y exists", "embedding": [1.0, 0.0]},
            ]
        ),
    )
    monkeypatch.setattr(s, "_embedding_dedupe", AsyncMock(return_value=(s._pending, [])))
    monkeypatch.setattr(
        s,
        "_call_primary_llm",
        AsyncMock(
            return_value={
                "new_insights": [{"content": "X depends on Y", "insight_type": "fact"}],
                "updates": [],
                "conflicts": [],
                "skipped": [],
            }
        ),
    )
    monkeypatch.setattr(
        s,
        "_write_new_insights",
        AsyncMock(
            return_value=(
                1,
                0,
                [{"id": "insight:new", "content": "X depends on Y", "embedding": [1.0, 0.0]}],
            )
        ),
    )

    fired = {}

    def spy(new_records, existing):
        fired["records"] = new_records
        fired["existing"] = existing
        return None  # don't actually schedule in the test

    monkeypatch.setattr(s, "_maybe_cognify", spy)

    await s.synthesize()
    assert fired["records"][0]["id"] == "insight:new"
    assert fired["existing"][0]["id"] == "insight:cand"


@pytest.mark.asyncio
async def test_synthesize_schedules_live_cognify_task(monkeypatch):
    """End-to-end: synthesize() spawns a real create_task(cognify(...)) and it runs."""
    import asyncio

    import core.engine.capture.synthesizer as syn

    monkeypatch.setattr(syn.settings, "cognify_enabled", True)
    s = _synth()
    s._pending = [{"id": "obs:1", "content": "X depends on Y", "discipline_hint": "architecture"}]

    monkeypatch.setattr(
        s,
        "_load_existing_insights",
        AsyncMock(
            return_value=[
                {"id": "insight:cand", "content": "Y exists", "embedding": [1.0, 0.0]},
            ]
        ),
    )
    monkeypatch.setattr(s, "_embedding_dedupe", AsyncMock(return_value=(s._pending, [])))
    monkeypatch.setattr(
        s,
        "_call_primary_llm",
        AsyncMock(
            return_value={
                "new_insights": [{"content": "X depends on Y", "insight_type": "fact"}],
                "updates": [],
                "conflicts": [],
                "skipped": [],
            }
        ),
    )
    monkeypatch.setattr(
        s,
        "_write_new_insights",
        AsyncMock(
            return_value=(
                1,
                0,
                [{"id": "insight:new", "content": "X depends on Y", "embedding": [1.0, 0.0]}],
            )
        ),
    )

    # Gate the fake cognify on an event the test controls, so the scheduled task
    # is still PENDING when synthesize() returns — synthesize()'s own post-write
    # awaits (event emits, emergence check) would otherwise run a fast task to
    # completion before we can observe it. This proves the seam is genuinely
    # fire-and-forget: the task outlives the hot path.
    release = asyncio.Event()
    seen = {}

    async def gated_cognify(new_records, find_candidates, **kw):
        seen["records"] = new_records
        await release.wait()
        return 1

    monkeypatch.setattr(syn, "cognify", gated_cognify)  # module-level name used by _maybe_cognify

    await s.synthesize()
    # A live task was scheduled (not awaited on the hot path) and is still pending.
    tasks = list(s._cognify_tasks)
    assert len(tasks) == 1
    assert not tasks[0].done()

    # Release it and drain deterministically.
    release.set()
    await asyncio.gather(*tasks)

    assert seen["records"][0]["id"] == "insight:new"
    # the done-callback removed the finished task from the tracking set
    assert s._cognify_tasks == set()


@pytest.mark.asyncio
async def test_flush_drains_pending_cognify_tasks():
    """Session-end flush() awaits fire-and-forget cognify tasks so edges aren't
    dropped when the process exits right after flush (the populate-as-you-go path)."""
    import asyncio

    s = _synth()
    s._pending = []  # nothing to synthesize; we're testing the drain itself

    ran = []

    async def slow_edge_write():
        await asyncio.sleep(0.01)
        ran.append(True)

    t = asyncio.create_task(slow_edge_write())
    s._cognify_tasks.add(t)
    t.add_done_callback(s._cognify_tasks.discard)

    await s.flush()

    assert t.done(), "flush() returned before the pending cognify task completed"
    assert ran == [True]
    assert s._cognify_tasks == set()  # done-callback cleared the tracking set
