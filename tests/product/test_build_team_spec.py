"""TDD: SpecGenerator.from_request_with_team — research → committee → risk → synthesize."""

import pytest

from core.engine.orchestration.composition_scorer import ScoredLensComposition
from core.engine.product import spec_generator as sg


def _ret(v):
    async def f(*a, **k):
        return v

    return f


@pytest.mark.integration
async def test_from_request_with_team_runs_four_stages(monkeypatch):
    """The team path runs research → committee → risk → synthesize, and the
    resulting spec is team-authored with the dynamic roster and risk recorded."""
    from core.engine.orchestration.deep_committee import CommitteeResult

    # Stage 2: classification + dynamic lenses + committee
    monkeypatch.setattr(
        sg, "classify_task", _ret({"discipline": "architecture", "specialties": ["security-hardening"]})
    )
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: ["architecture", "security"])
    monkeypatch.setattr(sg, "score_lens_composition", _ret(ScoredLensComposition()))
    monkeypatch.setattr(
        sg,
        "run_deep_committee",
        _ret(
            CommitteeResult(
                lens_outputs={"architecture": "a", "security": "s"},
                lens_lineage={"architecture": [], "security": []},
                synthesis="syn",
            )
        ),
    )

    gen = sg.SpecGenerator(db_pool=None)
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        _ret({"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}),
        raising=False,
    )
    monkeypatch.setattr(gen, "_assess_risk", _ret({"risk": "watch encodings", "blast_radius": {}}), raising=False)
    monkeypatch.setattr(
        gen._llm,
        "complete_json",
        _ret(
            {
                "objective": "redesign importer",
                "acceptance_criteria": [],
                "constraints": [],
                "integration_points": [],
                "estimated_files": [],
                "test_requirements": [],
                "best_practices": [],
            }
        ),
    )

    # bypass DB persistence
    async def _fake_persist(data, source, cap, product_id):
        return {**data}

    monkeypatch.setattr(gen, "_persist_spec", _fake_persist, raising=False)
    monkeypatch.setattr(gen, "_capture_spec_decision", _ret(None), raising=False)

    out = await gen.from_request_with_team("redesign importer", "product:platform")
    assert out["authored_by"] == "build_team"
    assert out["team_roster"] == ["architecture", "security"]
    assert out["team_lineage"] == {"architecture": "a", "security": "s"}
    assert out["risk"] == "watch encodings"
    assert out["objective"] == "redesign importer"


@pytest.mark.unit
async def test_persist_spec_passes_team_fields_to_create_query():
    """Regression: _persist_spec must include authored_by/team_roster/team_lineage/risk
    in the CREATE statement. The SCHEMALESS agent_spec table accepts the fields,
    but they have to be named in the SET clause and bound in the params dict —
    a prior bug had them silently dropped at this layer."""
    captured_params: dict = {}
    captured_query: str = ""

    class _FakeDB:
        async def query(self, query, params=None):
            nonlocal captured_query
            captured_query = query
            captured_params.update(params or {})
            return [{"result": [{"id": "agent_spec:fake"}]}]

    class _FakeConn:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *exc):
            return False

    class _FakePool:
        def connection(self):
            return _FakeConn()

    gen = sg.SpecGenerator(db_pool=_FakePool())

    spec_data = {
        "objective": "test",
        "acceptance_criteria": [],
        "constraints": [],
        "integration_points": [],
        "estimated_files": [],
        "test_requirements": [],
        "best_practices": [],
        "authored_by": "build_team",
        "team_roster": ["architecture", "security"],
        "team_lineage": {"architecture": "deep arch take", "security": "deep sec take"},
        "risk": "watch encodings",
    }
    await gen._persist_spec(spec_data, "human", None, "product:platform")

    # The query must name the team fields in the SET clause
    assert "authored_by = $authored_by" in captured_query
    assert "team_roster = $team_roster" in captured_query
    assert "team_lineage = $team_lineage" in captured_query
    assert "risk = $risk" in captured_query

    # And the params must carry their values
    assert captured_params["authored_by"] == "build_team"
    assert captured_params["team_roster"] == ["architecture", "security"]
    assert captured_params["team_lineage"] == {
        "architecture": "deep arch take",
        "security": "deep sec take",
    }
    assert captured_params["risk"] == "watch encodings"


@pytest.mark.unit
async def test_persist_spec_defaults_to_solo_for_non_team_paths():
    """from_gap/from_idea/from_request don't set authored_by — persistence
    must default it to 'solo' (not NONE) so clients can always read the field."""
    captured_params: dict = {}

    class _FakeDB:
        async def query(self, query, params=None):
            captured_params.update(params or {})
            return [{"result": [{"id": "agent_spec:fake"}]}]

    class _FakeConn:
        async def __aenter__(self):
            return _FakeDB()

        async def __aexit__(self, *exc):
            return False

    class _FakePool:
        def connection(self):
            return _FakeConn()

    gen = sg.SpecGenerator(db_pool=_FakePool())
    spec_data = {
        "objective": "test",
        "acceptance_criteria": [],
        "constraints": [],
        "integration_points": [],
        "estimated_files": [],
        "test_requirements": [],
        "best_practices": [],
    }
    await gen._persist_spec(spec_data, "human", None, "product:platform")

    assert captured_params["authored_by"] == "solo"
    assert captured_params["team_roster"] == []
    assert captured_params["team_lineage"] == {}
    assert captured_params["risk"] == ""
