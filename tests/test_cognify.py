# tests/test_cognify.py
import pytest

from core.engine.capture import cognify


class _Extraction:  # mimics the structured pydantic result
    def __init__(self, relations):
        self.relations = relations


class _Rel:
    def __init__(self, candidate_index, edge_type, new_is_source, confidence):
        self.candidate_index = candidate_index
        self.edge_type = edge_type
        self.new_is_source = new_is_source
        self.confidence = confidence


class _FakeLLM:
    def __init__(self, result):
        self._result = result
        self.calls = 0

    async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
        self.calls += 1
        return self._result


async def _candidates_for(_insight):
    return [{"id": "insight:c1", "content": "cand one"}, {"id": "insight:c2", "content": "cand two"}]


@pytest.mark.asyncio
async def test_extract_returns_edge_proposals_above_floor(monkeypatch):
    result = _Extraction(
        [
            _Rel(candidate_index=0, edge_type="informed_by", new_is_source=True, confidence=0.9),
            _Rel(candidate_index=1, edge_type="none", new_is_source=True, confidence=0.9),  # dropped: none
        ]
    )
    monkeypatch.setattr(cognify, "get_llm", lambda: _FakeLLM(result))

    props = await cognify.extract_relationships(
        [{"id": "insight:new", "content": "new insight"}],
        find_candidates=_candidates_for,
        min_confidence=0.5,
    )

    assert len(props) == 1
    p = props[0]
    assert p.edge_type == "informed_by"
    assert (p.from_id, p.to_id) == ("insight:new", "insight:c1")  # new_is_source → new -> candidate
    assert p.confidence == 0.9


@pytest.mark.asyncio
async def test_extract_drops_below_floor_unknown_type_and_self(monkeypatch):
    result = _Extraction(
        [
            _Rel(candidate_index=0, edge_type="informed_by", new_is_source=True, confidence=0.2),  # below floor
            _Rel(candidate_index=1, edge_type="not_a_type", new_is_source=True, confidence=0.9),  # unknown type
            _Rel(candidate_index=9, edge_type="solves", new_is_source=True, confidence=0.9),  # bad index
        ]
    )
    monkeypatch.setattr(cognify, "get_llm", lambda: _FakeLLM(result))
    props = await cognify.extract_relationships(
        [{"id": "insight:new", "content": "x"}],
        find_candidates=_candidates_for,
        min_confidence=0.5,
    )
    assert props == []


@pytest.mark.asyncio
async def test_extract_no_candidates_skips_llm(monkeypatch):
    fake = _FakeLLM(_Extraction([]))
    monkeypatch.setattr(cognify, "get_llm", lambda: fake)

    async def _none(_i):
        return []

    props = await cognify.extract_relationships(
        [{"id": "insight:new", "content": "x"}],
        find_candidates=_none,
        min_confidence=0.5,
    )
    assert props == []
    assert fake.calls == 0  # cost-gated: no candidates → no LLM call


@pytest.mark.asyncio
async def test_extract_is_non_fatal_on_llm_error(monkeypatch):
    class _Boom:
        async def complete_structured(self, *a, **k):
            raise RuntimeError("llm down")

    monkeypatch.setattr(cognify, "get_llm", lambda: _Boom())
    props = await cognify.extract_relationships(
        [{"id": "insight:new", "content": "x"}],
        find_candidates=_candidates_for,
        min_confidence=0.5,
    )
    assert props == []  # never raises


@pytest.mark.asyncio
async def test_cognify_creates_assertions_and_returns_count(monkeypatch):
    result = _Extraction(
        [
            _Rel(candidate_index=0, edge_type="informed_by", new_is_source=True, confidence=0.9),
            _Rel(candidate_index=1, edge_type="causes", new_is_source=False, confidence=0.8),
        ]
    )
    monkeypatch.setattr(cognify, "get_llm", lambda: _FakeLLM(result))

    created = []

    async def fake_persist(proposals, **kwargs):
        created.extend(proposals)
        return [{"ok": True}]

    monkeypatch.setattr(cognify, "persist_resolution", fake_persist)

    n = await cognify.cognify(
        [{"id": "insight:new", "content": "x"}],
        find_candidates=_candidates_for,
        min_confidence=0.5,
    )

    assert n == 2
    assert any(
        p.predicate == "informed_by" and p.subject == "insight:new" and p.object == "insight:c1" for p in created
    )
    assert any(p.predicate == "causes" and p.subject == "insight:c2" and p.object == "insight:new" for p in created)


@pytest.mark.asyncio
async def test_cognify_non_fatal_when_assertion_batch_write_fails(monkeypatch):
    result = _Extraction(
        [
            _Rel(candidate_index=0, edge_type="informed_by", new_is_source=True, confidence=0.9),
            _Rel(candidate_index=1, edge_type="solves", new_is_source=True, confidence=0.9),
        ]
    )
    monkeypatch.setattr(cognify, "get_llm", lambda: _FakeLLM(result))

    async def flaky_persist(proposals, **kwargs):
        raise RuntimeError("assertion store unavailable")

    monkeypatch.setattr(cognify, "persist_resolution", flaky_persist)
    n = await cognify.cognify(
        [{"id": "insight:new", "content": "x"}], find_candidates=_candidates_for, min_confidence=0.5
    )
    assert n == 0  # batch failed explicitly; capture still never raises


@pytest.mark.asyncio
async def test_cognify_zero_when_no_proposals(monkeypatch):
    monkeypatch.setattr(cognify, "get_llm", lambda: _FakeLLM(_Extraction([])))

    async def fake_persist(*a, **k):
        raise AssertionError("should not persist assertions")

    monkeypatch.setattr(cognify, "persist_resolution", fake_persist)
    n = await cognify.cognify([{"id": "insight:new", "content": "x"}], find_candidates=_candidates_for)
    assert n == 0
