from __future__ import annotations

import pytest

import core.engine.arms.strategy.graph_classifier as gc


def test_verify_for_risk_mapping():
    assert gc._verify_for_risk("isolated") == "smoke"
    assert gc._verify_for_risk("connected") == "unit"
    assert gc._verify_for_risk("systemic") == "full"
    assert gc._verify_for_risk("nonsense") == "unit"  # unknown -> safe middle


def test_coerce_accepts_valid_rejects_invalid():
    assert gc._coerce("module", gc._SCOPE) == "module"
    assert gc._coerce("brandnew", gc._NOVELTY) is None
    assert gc._coerce(None, gc._RISK) is None
    assert gc._coerce(123, gc._SCOPE) is None


@pytest.fixture(autouse=True)
def _clear_scan_guard():
    """Module-level _scan_kicked must not bleed across tests."""
    gc._scan_kicked.clear()
    yield
    gc._scan_kicked.clear()


def _stub_graph(monkeypatch, *, hits=None, affected=0, scans=None):
    """Stub the code-graph I/O wrappers. `scans` is a list to record scan calls."""

    async def fake_search(intent):
        return {"results": hits or [], "total": len(hits or [])}

    async def fake_blast(path, product_id):
        return {"total_affected": affected, "affected_files": []}

    async def fake_scan(product_id):
        (scans if scans is not None else []).append(product_id)
        return {"status": "started"}

    monkeypatch.setattr(gc, "_search_code", fake_search)
    monkeypatch.setattr(gc, "_blast_radius", fake_blast)
    monkeypatch.setattr(gc, "_scan", fake_scan)


@pytest.mark.asyncio
async def test_measure_warm_single_file_small_blast(monkeypatch):
    # Real hybrid_search rows are keyed `path` and carry `semantic_score`.
    _stub_graph(monkeypatch, hits=[{"path": "a.py", "semantic_score": 0.9}], affected=1)
    out = await gc._measure_from_code_graph("intent", "product:platform")
    assert out == {"scope": "nearby", "risk": "isolated"}


@pytest.mark.asyncio
async def test_measure_warm_many_files_large_blast(monkeypatch):
    hits = [{"path": f"m/f{i}.py", "semantic_score": 0.8} for i in range(5)]
    _stub_graph(monkeypatch, hits=hits, affected=20)
    out = await gc._measure_from_code_graph("intent", "product:platform")
    assert out == {"scope": "repo", "risk": "systemic"}


@pytest.mark.asyncio
async def test_measure_blast_silent_returns_scope_only(monkeypatch):
    _stub_graph(
        monkeypatch, hits=[{"path": "a.py", "semantic_score": 0.7}, {"path": "b.py", "semantic_score": 0.7}], affected=0
    )
    out = await gc._measure_from_code_graph("intent", "product:platform")
    assert out == {"scope": "module"}  # 2 files -> module; risk omitted (blast silent)


@pytest.mark.asyncio
async def test_measure_keyword_only_hits_are_not_measured(monkeypatch):
    # Embeddings down -> keyword fallback returns semantic_score 0.0; must NOT be treated as
    # precise scope (it would wrongly outrank LLM reasoning), and must NOT trigger a rescan
    # (the graph has files; scanning won't restore embeddings).
    scans = []
    _stub_graph(
        monkeypatch,
        hits=[{"path": "a.py", "semantic_score": 0.0}, {"path": "b.py", "semantic_score": 0.0}],
        affected=5,
        scans=scans,
    )
    out = await gc._measure_from_code_graph("intent", "product:platform")
    assert out == {}  # keyword noise -> let reasoning fill
    assert scans == []  # not cold -> no rescan


@pytest.mark.asyncio
async def test_measure_cold_graph_kicks_scan_once(monkeypatch):
    scans = []
    _stub_graph(monkeypatch, hits=[], affected=0, scans=scans)
    out1 = await gc._measure_from_code_graph("intent", "product:platform")
    out2 = await gc._measure_from_code_graph("intent", "product:platform")
    assert out1 == {} and out2 == {}  # cold -> measures nothing
    assert scans == ["product:platform"]  # scan kicked EXACTLY once per product/process


@pytest.mark.asyncio
async def test_measure_swallows_search_error(monkeypatch):
    async def boom(intent):
        raise RuntimeError("graph down")

    monkeypatch.setattr(gc, "_search_code", boom)
    out = await gc._measure_from_code_graph("intent", "product:platform")
    assert out == {}  # non-fatal


class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload

    async def complete_json(self, prompt):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.mark.asyncio
async def test_knowledge_context_digests_results(monkeypatch):
    # Real ace_search rows carry `content`; tolerate legacy `text`/`summary` too.
    async def fake_know(intent, product_id):
        return {
            "results": [{"content": "auth module uses caching"}, {"text": "legacy text key"}, {"summary": "tension X"}],
            "count": 3,
        }

    monkeypatch.setattr(gc, "_knowledge_search", fake_know)
    out = await gc._knowledge_context("intent", "product:platform")
    assert "auth module uses caching" in out and "legacy text key" in out and "tension X" in out


@pytest.mark.asyncio
async def test_knowledge_context_empty_on_error(monkeypatch):
    async def boom(intent, product_id):
        raise RuntimeError("search down")

    monkeypatch.setattr(gc, "_knowledge_search", boom)
    assert await gc._knowledge_context("intent", "product:platform") == ""


@pytest.mark.asyncio
async def test_reason_profile_coerces_and_keeps_valid(monkeypatch):
    monkeypatch.setattr(
        gc,
        "get_llm",
        lambda: _FakeLLM({"novelty": "extend", "task_type": "add caching", "scope": "module", "risk": "connected"}),
    )
    out = await gc._reason_profile("intent", None, "")
    assert out == {"novelty": "extend", "task_type": "add caching", "scope": "module", "risk": "connected"}


@pytest.mark.asyncio
async def test_reason_profile_drops_invalid_enums(monkeypatch):
    monkeypatch.setattr(gc, "get_llm", lambda: _FakeLLM({"novelty": "brandnew", "scope": "galaxy", "task_type": "x"}))
    out = await gc._reason_profile("intent", None, "")
    assert out == {"task_type": "x"}  # invalid novelty/scope dropped; no risk key


@pytest.mark.asyncio
async def test_reason_profile_empty_on_llm_error(monkeypatch):
    monkeypatch.setattr(gc, "get_llm", lambda: _FakeLLM(RuntimeError("llm down")))
    assert await gc._reason_profile("intent", None, "") == {}


from core.engine.arms.strategy.profile import WorkProfile
from core.engine.solution import Solution


def _stub_all(monkeypatch, *, measured, reasoned):
    async def fake_measure(intent, product_id):
        return dict(measured)

    async def fake_knowledge(intent, product_id):
        return "ctx"

    async def fake_reason(intent, conversation, knowledge):
        return dict(reasoned)

    monkeypatch.setattr(gc, "_measure_from_code_graph", fake_measure)
    monkeypatch.setattr(gc, "_knowledge_context", fake_knowledge)
    monkeypatch.setattr(gc, "_reason_profile", fake_reason)


@pytest.mark.asyncio
async def test_classifier_warm_measured_wins_for_scope_risk(monkeypatch):
    _stub_all(
        monkeypatch,
        measured={"scope": "repo", "risk": "systemic"},
        reasoned={"scope": "nearby", "risk": "isolated", "novelty": "extend", "task_type": "t"},
    )
    p = await gc.graph_grounded_classifier(Solution(intent="x", domain_hint="code"))
    assert (p.scope, p.risk) == ("repo", "systemic")  # measured wins
    assert (p.novelty, p.task_type) == ("extend", "t")  # reasoned supplies these
    assert p.verify_depth == "full"  # derived from risk


@pytest.mark.asyncio
async def test_classifier_cold_graph_uses_reasoning_not_greenfield(monkeypatch):
    # The real-repo case: code graph silent (measured={}), reasoning says modify, not greenfield.
    _stub_all(
        monkeypatch,
        measured={},
        reasoned={"scope": "module", "risk": "connected", "novelty": "modify", "task_type": "tweak"},
    )
    p = await gc.graph_grounded_classifier(Solution(intent="add a flag", domain_hint="code"))
    assert p.novelty == "modify"  # NOT forced to greenfield by empty graph
    assert (p.scope, p.risk) == ("module", "connected")
    assert p.verify_depth == "unit"


@pytest.mark.asyncio
async def test_classifier_all_silent_returns_middle(monkeypatch):
    _stub_all(monkeypatch, measured={}, reasoned={})
    p = await gc.graph_grounded_classifier(Solution(intent="x", domain_hint="code"))
    default = WorkProfile()
    assert (p.scope, p.novelty, p.risk, p.task_type) == (
        default.scope,
        default.novelty,
        default.risk,
        default.task_type,
    )
    assert p.verify_depth == gc._verify_for_risk(default.risk)


@pytest.mark.asyncio
async def test_classifier_accepts_overrides_arg_without_applying(monkeypatch):
    # classify_work applies overrides; the classifier just must accept the positional arg.
    _stub_all(monkeypatch, measured={}, reasoned={"novelty": "fix"})
    p = await gc.graph_grounded_classifier(
        Solution(intent="x", domain_hint="code"), "conversation text", {"scope": "repo"}
    )
    assert p.novelty == "fix"
    assert p.scope == WorkProfile().scope  # override NOT applied here (classify_work does that)


@pytest.mark.asyncio
async def test_classifier_scopes_graph_queries_to_solution_product(monkeypatch):
    # The Solution's product_id must reach the graph/knowledge queries, not the hard default —
    # otherwise multi-product knowledge grounding silently reads the wrong product.
    seen = {}

    async def fake_measure(intent, product_id):
        seen["measure"] = product_id
        return {}

    async def fake_knowledge(intent, product_id):
        seen["knowledge"] = product_id
        return ""

    async def fake_reason(intent, conversation, knowledge):
        return {}

    monkeypatch.setattr(gc, "_measure_from_code_graph", fake_measure)
    monkeypatch.setattr(gc, "_knowledge_context", fake_knowledge)
    monkeypatch.setattr(gc, "_reason_profile", fake_reason)

    sol = Solution(intent="x", domain_hint="code")
    sol.product_id = "product:acme"
    await gc.graph_grounded_classifier(sol)
    assert seen == {"measure": "product:acme", "knowledge": "product:acme"}
