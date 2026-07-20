"""Integration: from_request_with_team enforces BATS call-budget.

When the deep committee fires more agent.phase.end events than the call
budget allows, the risk pass is skipped and the risk text reports the cap."""

import pytest

from core.engine.orchestration.composition_scorer import ScoredLensComposition


def _ret(v):
    async def f(*a, **k):
        return v

    return f


@pytest.mark.integration
async def test_assess_risk_skipped_when_call_budget_exceeded(monkeypatch):
    """When phase.end events ≥ call_budget, _assess_risk is NOT invoked."""
    from core.engine.orchestration.deep_committee import CommitteeResult
    from core.engine.product import spec_generator as sg

    monkeypatch.setattr(
        sg,
        "classify_task",
        _ret({"discipline": "architecture", "specialties": [], "complexity": "simple", "mode": "reactive"}),
    )  # budget=4
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: ["architecture"])
    monkeypatch.setattr(sg, "score_lens_composition", _ret(ScoredLensComposition()))

    async def _fake_committee(*args, **kwargs):
        cb = kwargs.get("event_callback")
        if cb is not None:
            for i in range(6):  # > budget=4
                await cb(
                    "agent.phase.end",
                    {
                        "lens": "architecture",
                        "phase_idx": i,
                        "cognitive_function": "frame",
                        "confidence": 0.9,
                    },
                )
        return CommitteeResult(lens_outputs={"architecture": "a"}, lens_lineage={}, synthesis="syn")

    monkeypatch.setattr(sg, "run_deep_committee", _fake_committee)
    gen = sg.SpecGenerator(db_pool=None)
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        _ret({"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}),
        raising=False,
    )

    assess_risk_invocations = []

    async def _record_assess_risk(request, product_id, committee):
        assess_risk_invocations.append(1)
        return {"risk": "should-not-be-called", "blast_radius": {}}

    monkeypatch.setattr(gen, "_assess_risk", _record_assess_risk, raising=False)
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
        return {**data}

    monkeypatch.setattr(gen, "_persist_spec", _fake_persist, raising=False)
    monkeypatch.setattr(gen, "_capture_spec_decision", _ret(None), raising=False)

    spec = await gen.from_request_with_team("rebuild importer", "product:platform")

    assert assess_risk_invocations == []  # NOT invoked
    assert spec["risk"] == "(skipped: call budget exceeded)"
    assert spec["objective"] == "x"  # synthesis still ran


@pytest.mark.integration
async def test_risk_runs_when_call_count_under_budget(monkeypatch):
    """When phase event count stays under the budget, _assess_risk runs normally."""
    from core.engine.orchestration.deep_committee import CommitteeResult
    from core.engine.product import spec_generator as sg

    monkeypatch.setattr(
        sg,
        "classify_task",
        _ret({"discipline": "architecture", "specialties": [], "complexity": "complex", "mode": "deliberative"}),
    )  # budget=16
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: ["architecture"])
    monkeypatch.setattr(sg, "score_lens_composition", _ret(ScoredLensComposition()))

    async def _fake_committee(*args, **kwargs):
        cb = kwargs.get("event_callback")
        if cb is not None:
            for i in range(3):  # well under 16
                await cb(
                    "agent.phase.end",
                    {
                        "lens": "architecture",
                        "phase_idx": i,
                        "cognitive_function": "frame",
                        "confidence": 0.9,
                    },
                )
        return CommitteeResult(lens_outputs={"architecture": "a"}, lens_lineage={}, synthesis="syn")

    monkeypatch.setattr(sg, "run_deep_committee", _fake_committee)
    gen = sg.SpecGenerator(db_pool=None)
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        _ret({"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}),
        raising=False,
    )
    monkeypatch.setattr(gen, "_assess_risk", _ret({"risk": "real-risk-text", "blast_radius": {}}), raising=False)
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
        return {**data}

    monkeypatch.setattr(gen, "_persist_spec", _fake_persist, raising=False)
    monkeypatch.setattr(gen, "_capture_spec_decision", _ret(None), raising=False)

    spec = await gen.from_request_with_team("rebuild importer", "product:platform")
    assert spec["risk"] == "real-risk-text"
