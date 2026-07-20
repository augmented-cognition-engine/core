"""Integration: from_request_with_team emits one composition_signal per lens."""

import pytest


def _ret(v):
    async def f(*a, **k):
        return v

    return f


@pytest.mark.integration
async def test_emits_one_signal_per_lens(monkeypatch):
    """A 3-lens team build writes 3 composition_signal rows with lens+lens_set+recipe_slug."""
    from core.engine.orchestration.deep_committee import CommitteeResult
    from core.engine.product import spec_generator as sg

    monkeypatch.setattr(
        sg,
        "classify_task",
        _ret(
            {
                "discipline": "architecture",
                "specialties": [],
                "complexity": "moderate",
                "mode": "deliberative",
                "mode_confidence": 0.9,
                "archetype": "creator",
                "engagement": {"perspectives": ["practitioner"]},
            }
        ),
    )
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: ["architecture", "security", "data"])

    async def _fake_committee(*args, **kwargs):
        cb = kwargs.get("event_callback")
        if cb is not None:
            for lens in ["architecture", "security", "data"]:
                await cb(
                    "agent.phase.end",
                    {
                        "lens": lens,
                        "phase_idx": 0,
                        "cognitive_function": "frame",
                        "confidence": 0.85,
                    },
                )
        return CommitteeResult(
            lens_outputs={"architecture": "arch out", "security": "sec out", "data": "data out"},
            lens_lineage={
                "architecture": [{"cognitive_function": "frame", "output": "x", "confidence": 0.85}],
                "security": [{"cognitive_function": "frame", "output": "x", "confidence": 0.88}],
                "data": [{"cognitive_function": "frame", "output": "x", "confidence": 0.82}],
            },
            synthesis="syn",
            recipe_slugs={
                "architecture": "systems_intelligence",
                "security": "risk_intelligence",
                "data": "data_intelligence",
            },
        )

    monkeypatch.setattr(sg, "run_deep_committee", _fake_committee)

    # Capture composition_signal writes
    captured_signals: list[dict] = []

    class _FakeDB:
        async def query(self, q, params=None):
            if "CREATE composition_signal" in q:
                captured_signals.append(params or {})
                return [{"result": [{"id": "composition_signal:fake"}]}]
            return []

    class _FakeConn:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *exc):
            return False

    class _FakePool:
        def connection(self):
            return _FakeConn()

    gen = sg.SpecGenerator(db_pool=_FakePool())
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        _ret({"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}),
        raising=False,
    )
    monkeypatch.setattr(gen, "_assess_risk", _ret({"risk": "r", "blast_radius": {}}), raising=False)
    monkeypatch.setattr(
        gen._llm,
        "complete_json",
        _ret(
            {
                "objective": "x",
                "acceptance_criteria": [],
                "constraints": [],
                "integration_points": [],
                "estimated_files": [],
                "test_requirements": [],
                "best_practices": [],
            }
        ),
    )

    async def _fake_persist(data, source, cap, product_id):
        return {**data, "id": "agent_spec:fake"}

    monkeypatch.setattr(gen, "_persist_spec", _fake_persist, raising=False)
    monkeypatch.setattr(gen, "_capture_spec_decision", _ret(None), raising=False)

    # Bypass scorer (Task 5 wires it; Task 4 just emits signals)
    from core.engine.orchestration import composition_scorer as cs
    from core.engine.orchestration.composition_scorer import ScoredLensComposition

    async def _no_score(*a, **k):
        return ScoredLensComposition()

    monkeypatch.setattr(cs, "score_lens_composition", _no_score)
    monkeypatch.setattr(sg, "score_lens_composition", _no_score, raising=False)

    await gen.from_request_with_team("redesign importer", "product:platform")

    # 3 lens → 3 composition_signal rows
    assert len(captured_signals) == 3, f"expected 3 signals; got {len(captured_signals)}"

    # Each row has the right lens + lens_set + recipe_slug
    by_lens = {s["lens"]: s for s in captured_signals}
    assert set(by_lens.keys()) == {"architecture", "security", "data"}
    for sig in captured_signals:
        assert sig["lens_set"] == ["architecture", "security", "data"]
        assert sig["discipline"] == sig["lens"]  # team-build row: discipline=lens
        assert sig["recipe_slug"] is not None
        assert sig["engagement_type"] == "deep_committee"


@pytest.mark.integration
async def test_signal_write_failure_does_not_raise(monkeypatch):
    """If signal-write throws, from_request_with_team still returns the spec."""
    from core.engine.orchestration.deep_committee import CommitteeResult
    from core.engine.product import spec_generator as sg

    monkeypatch.setattr(
        sg,
        "classify_task",
        _ret({"discipline": "architecture", "specialties": [], "complexity": "simple", "mode": "reactive"}),
    )
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: ["architecture"])

    async def _fake_committee(*args, **kwargs):
        return CommitteeResult(
            lens_outputs={"architecture": "a"},
            lens_lineage={"architecture": []},
            synthesis="s",
            recipe_slugs={"architecture": "systems_intelligence"},
        )

    monkeypatch.setattr(sg, "run_deep_committee", _fake_committee)

    # DB raises on composition_signal write
    class _FakeDB:
        async def query(self, q, params=None):
            if "CREATE composition_signal" in q:
                raise RuntimeError("DB on fire")
            return []

    class _FakeConn:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *exc):
            return False

    class _FakePool:
        def connection(self):
            return _FakeConn()

    gen = sg.SpecGenerator(db_pool=_FakePool())
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        _ret({"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}),
        raising=False,
    )
    monkeypatch.setattr(gen, "_assess_risk", _ret({"risk": "r", "blast_radius": {}}), raising=False)
    monkeypatch.setattr(
        gen._llm,
        "complete_json",
        _ret(
            {
                "objective": "ok",
                "acceptance_criteria": [],
                "constraints": [],
                "integration_points": [],
                "estimated_files": [],
                "test_requirements": [],
                "best_practices": [],
            }
        ),
    )

    async def _fake_persist(data, source, cap, product_id):
        return {**data, "id": "agent_spec:fake"}

    monkeypatch.setattr(gen, "_persist_spec", _fake_persist, raising=False)
    monkeypatch.setattr(gen, "_capture_spec_decision", _ret(None), raising=False)

    from core.engine.orchestration import composition_scorer as cs
    from core.engine.orchestration.composition_scorer import ScoredLensComposition

    async def _no_score(*a, **k):
        return ScoredLensComposition()

    monkeypatch.setattr(cs, "score_lens_composition", _no_score)
    monkeypatch.setattr(sg, "score_lens_composition", _no_score, raising=False)

    # Should NOT raise
    spec = await gen.from_request_with_team("rebuild", "product:platform")
    assert spec["objective"] == "ok"
