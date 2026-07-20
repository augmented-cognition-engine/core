"""Integration: from_request_with_team applies scorer adjustments to lens output."""

import pytest


def _ret(v):
    async def f(*a, **k):
        return v

    return f


def _spec_data():
    return {
        "objective": "x",
        "acceptance_criteria": [],
        "constraints": [],
        "integration_points": [],
        "estimated_files": [],
        "test_requirements": [],
        "best_practices": [],
    }


@pytest.mark.integration
async def test_scorer_filters_low_weight_lens(monkeypatch):
    """When the scorer returns lens_weights with a value < MIN_WEIGHT, that lens
    is filtered out of the final set passed to run_deep_committee."""
    from core.engine.orchestration.composition_scorer import ScoredLensComposition
    from core.engine.orchestration.deep_committee import CommitteeResult
    from core.engine.product import spec_generator as sg

    monkeypatch.setattr(
        sg,
        "classify_task",
        _ret({"discipline": "architecture", "specialties": [], "complexity": "moderate", "mode": "deliberative"}),
    )
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: ["architecture", "security"])

    # Scorer says architecture has weight 0.05 (below MIN_WEIGHT=0.1) — filter it out
    async def _score(*a, **k):
        return ScoredLensComposition(
            lens_weights={"architecture": 0.05, "security": 1.0},
            injected_lenses=[],
        )

    monkeypatch.setattr(sg, "score_lens_composition", _score)

    received_lenses: list[str] = []

    async def _fake_committee(*args, **kwargs):
        # kwargs may carry lenses; positional arg [1] is lenses too
        lenses_arg = args[1] if len(args) >= 2 else kwargs.get("lenses")
        received_lenses.extend(lenses_arg)
        return CommitteeResult(
            lens_outputs={lens: "out" for lens in lenses_arg},
            lens_lineage={lens: [] for lens in lenses_arg},
            synthesis="syn",
            recipe_slugs={lens: f"{lens}_intelligence" for lens in lenses_arg},
        )

    monkeypatch.setattr(sg, "run_deep_committee", _fake_committee)
    gen = sg.SpecGenerator(db_pool=None)
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        _ret({"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}),
        raising=False,
    )
    monkeypatch.setattr(gen, "_assess_risk", _ret({"risk": "r", "blast_radius": {}}), raising=False)
    monkeypatch.setattr(gen._llm, "complete_json", _ret(_spec_data()))

    async def _fake_persist(data, source, cap, product_id):
        return {**data, "id": "agent_spec:fake"}

    monkeypatch.setattr(gen, "_persist_spec", _fake_persist, raising=False)
    monkeypatch.setattr(gen, "_capture_spec_decision", _ret(None), raising=False)
    monkeypatch.setattr(gen, "_emit_team_signals", _ret(None), raising=False)

    await gen.from_request_with_team("rebuild", "product:platform")
    # architecture should have been filtered out; only security remains
    assert "architecture" not in received_lenses
    assert "security" in received_lenses


@pytest.mark.integration
async def test_scorer_injects_lens(monkeypatch):
    """When the scorer returns injected_lenses, they're appended to the base set."""
    from core.engine.orchestration.composition_scorer import ScoredLensComposition
    from core.engine.orchestration.deep_committee import CommitteeResult
    from core.engine.product import spec_generator as sg

    monkeypatch.setattr(
        sg,
        "classify_task",
        _ret({"discipline": "architecture", "specialties": [], "complexity": "moderate", "mode": "deliberative"}),
    )
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: ["architecture"])

    async def _score(*a, **k):
        return ScoredLensComposition(
            lens_weights={"architecture": 1.0},
            injected_lenses=["security"],
        )

    monkeypatch.setattr(sg, "score_lens_composition", _score)

    received_lenses: list[str] = []

    async def _fake_committee(*args, **kwargs):
        lenses_arg = args[1] if len(args) >= 2 else kwargs.get("lenses")
        received_lenses.extend(lenses_arg)
        return CommitteeResult(
            lens_outputs={lens: "out" for lens in lenses_arg},
            lens_lineage={lens: [] for lens in lenses_arg},
            synthesis="syn",
            recipe_slugs={lens: f"{lens}_intelligence" for lens in lenses_arg},
        )

    monkeypatch.setattr(sg, "run_deep_committee", _fake_committee)
    gen = sg.SpecGenerator(db_pool=None)
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        _ret({"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}),
        raising=False,
    )
    monkeypatch.setattr(gen, "_assess_risk", _ret({"risk": "r", "blast_radius": {}}), raising=False)
    monkeypatch.setattr(gen._llm, "complete_json", _ret(_spec_data()))

    async def _fake_persist(data, source, cap, product_id):
        return {**data, "id": "agent_spec:fake"}

    monkeypatch.setattr(gen, "_persist_spec", _fake_persist, raising=False)
    monkeypatch.setattr(gen, "_capture_spec_decision", _ret(None), raising=False)
    monkeypatch.setattr(gen, "_emit_team_signals", _ret(None), raising=False)

    await gen.from_request_with_team("rebuild", "product:platform")
    assert "architecture" in received_lenses
    assert "security" in received_lenses


@pytest.mark.integration
async def test_scorer_respects_max_lenses_cap(monkeypatch):
    """Injection cannot push the final set past MAX_LENSES."""
    from core.engine.orchestration.composition_scorer import ScoredLensComposition
    from core.engine.orchestration.deep_committee import MAX_LENSES, CommitteeResult
    from core.engine.product import spec_generator as sg

    monkeypatch.setattr(
        sg,
        "classify_task",
        _ret({"discipline": "architecture", "specialties": [], "complexity": "complex", "mode": "deliberative"}),
    )
    # Resolver returns MAX_LENSES already
    base = ["architecture", "security", "data", "performance"][:MAX_LENSES]
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: base)

    async def _score(*a, **k):
        return ScoredLensComposition(
            lens_weights={lens: 1.0 for lens in base},
            injected_lenses=["ux", "ai_ml"],  # would push past cap
        )

    monkeypatch.setattr(sg, "score_lens_composition", _score)

    received_lenses: list[str] = []

    async def _fake_committee(*args, **kwargs):
        lenses_arg = args[1] if len(args) >= 2 else kwargs.get("lenses")
        received_lenses.extend(lenses_arg)
        return CommitteeResult(
            lens_outputs={lens: "out" for lens in lenses_arg},
            lens_lineage={lens: [] for lens in lenses_arg},
            synthesis="syn",
            recipe_slugs={lens: f"{lens}_intelligence" for lens in lenses_arg},
        )

    monkeypatch.setattr(sg, "run_deep_committee", _fake_committee)
    gen = sg.SpecGenerator(db_pool=None)
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        _ret({"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}),
        raising=False,
    )
    monkeypatch.setattr(gen, "_assess_risk", _ret({"risk": "r", "blast_radius": {}}), raising=False)
    monkeypatch.setattr(gen._llm, "complete_json", _ret(_spec_data()))

    async def _fake_persist(data, source, cap, product_id):
        return {**data, "id": "agent_spec:fake"}

    monkeypatch.setattr(gen, "_persist_spec", _fake_persist, raising=False)
    monkeypatch.setattr(gen, "_capture_spec_decision", _ret(None), raising=False)
    monkeypatch.setattr(gen, "_emit_team_signals", _ret(None), raising=False)

    await gen.from_request_with_team("rebuild", "product:platform")
    assert len(received_lenses) <= MAX_LENSES
