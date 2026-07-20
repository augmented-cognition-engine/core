# tests/cognition/test_moa.py
import pytest
from pydantic import BaseModel

from core.engine.cognition import moa


class _Out(BaseModel):
    answer: str
    score: float = 0.5


class _FakeLLM:
    """complete_structured returns/raises per the model arg."""

    def __init__(self, by_model: dict):
        self.by_model = by_model

    async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
        v = self.by_model.get(model)
        if isinstance(v, Exception):
            raise v
        return v


@pytest.mark.asyncio
async def test_propose_returns_one_proposal_per_successful_model(monkeypatch):
    fake = _FakeLLM({"haiku": _Out(answer="A"), "sonnet": _Out(answer="B")})
    monkeypatch.setattr(moa, "get_llm", lambda: fake)

    props = await moa.propose("prompt", _Out, ["haiku", "sonnet"])

    assert len(props) == 2
    assert {p.model for p in props} == {"haiku", "sonnet"}
    assert {p.output.answer for p in props} == {"A", "B"}
    # raw is the JSON serialization of the parsed output (for downstream PhaseOutput parsing)
    assert all(p.raw and "answer" in p.raw for p in props)


@pytest.mark.asyncio
async def test_propose_drops_failed_models(monkeypatch):
    fake = _FakeLLM({"haiku": _Out(answer="A"), "opus": RuntimeError("boom")})
    monkeypatch.setattr(moa, "get_llm", lambda: fake)

    props = await moa.propose("prompt", _Out, ["haiku", "opus"])

    assert len(props) == 1
    assert props[0].model == "haiku"


@pytest.mark.asyncio
async def test_propose_all_fail_returns_empty(monkeypatch):
    fake = _FakeLLM({"haiku": RuntimeError("x"), "sonnet": RuntimeError("y")})
    monkeypatch.setattr(moa, "get_llm", lambda: fake)

    props = await moa.propose("prompt", _Out, ["haiku", "sonnet"])
    assert props == []


@pytest.mark.asyncio
async def test_aggregate_synthesizes_from_proposals(monkeypatch):
    props = [
        moa.Proposal("haiku", _Out(answer="A"), '{"answer":"A","score":0.5}'),
        moa.Proposal("sonnet", _Out(answer="B"), '{"answer":"B","score":0.5}'),
    ]
    captured = {}

    class _AggLLM:
        async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
            captured["prompt"] = prompt
            captured["model"] = model
            return _Out(answer="synthesized")

    monkeypatch.setattr(moa, "get_llm", lambda: _AggLLM())

    agg = await moa.aggregate(props, task="decide X", schema=_Out, aggregator_model="opus")

    assert agg is not None
    assert agg.model == "opus"
    assert agg.output.answer == "synthesized"
    assert agg.raw and "synthesized" in agg.raw
    # both proposals' content + the task are in the synthesis prompt
    assert "A" in captured["prompt"] and "B" in captured["prompt"] and "decide X" in captured["prompt"]
    assert captured["model"] == "opus"


@pytest.mark.asyncio
async def test_aggregate_empty_proposals_returns_none(monkeypatch):
    monkeypatch.setattr(moa, "get_llm", lambda: object())
    assert await moa.aggregate([], task="t", schema=_Out, aggregator_model="opus") is None


@pytest.mark.asyncio
async def test_aggregate_failure_returns_none(monkeypatch):
    props = [moa.Proposal("haiku", _Out(answer="A"), '{"answer":"A"}')]

    class _BoomLLM:
        async def complete_structured(self, *a, **k):
            raise RuntimeError("aggregator down")

    monkeypatch.setattr(moa, "get_llm", lambda: _BoomLLM())
    assert await moa.aggregate(props, task="t", schema=_Out, aggregator_model="opus") is None
