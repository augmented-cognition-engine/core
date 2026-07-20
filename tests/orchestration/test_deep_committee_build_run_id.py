"""Backend tests for the canvas team-build surface: build_run_id propagation
and the build.team_resolved event."""

import pytest

from core.engine.orchestration.composition_scorer import ScoredLensComposition


def _async_ret(v):
    """Return an async callable that always resolves to v."""

    async def f(*a, **k):
        return v

    return f


@pytest.mark.unit
def test_build_team_resolved_event_constant_exists():
    """EVENT_BUILD_TEAM_RESOLVED must be defined and included in ALL_EVENT_TYPES."""
    from core.engine.canvas.event_protocol import ALL_EVENT_TYPES, EVENT_BUILD_TEAM_RESOLVED

    assert EVENT_BUILD_TEAM_RESOLVED == "build.team_resolved"
    assert EVENT_BUILD_TEAM_RESOLVED in ALL_EVENT_TYPES


@pytest.mark.integration
async def test_build_run_id_propagates_to_event_callback(monkeypatch):
    """Every event_callback invocation from from_request_with_team must carry the
    same build_run_id, and distinct calls generate distinct ids."""
    from core.engine.orchestration.deep_committee import CommitteeResult
    from core.engine.product import spec_generator as sg

    captured: list[dict] = []

    async def _on_event(event_type, payload):
        captured.append({"event_type": event_type, **payload})

    async def _fake_committee(*args, **kwargs):
        # Simulate the committee firing one phase event through the wrapped callback.
        cb = kwargs.get("event_callback")
        if cb is not None:
            await cb(
                "agent.phase.end",
                {
                    "lens": "architecture",
                    "phase_idx": 0,
                    "cognitive_function": "frame",
                    "confidence": 0.9,
                },
            )
        return CommitteeResult(lens_outputs={"architecture": "a"}, lens_lineage={}, synthesis="syn")

    async def _ret(v):
        return v

    monkeypatch.setattr(sg, "classify_task", lambda *a, **k: _ret({"discipline": "architecture", "specialties": []}))
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: ["architecture"])
    monkeypatch.setattr(sg, "score_lens_composition", _async_ret(ScoredLensComposition()))
    monkeypatch.setattr(sg, "run_deep_committee", _fake_committee)

    gen = sg.SpecGenerator(db_pool=None)
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        lambda *a, **k: _ret(
            {"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}
        ),
        raising=False,
    )
    monkeypatch.setattr(gen, "_assess_risk", lambda *a, **k: _ret({"risk": "", "blast_radius": {}}), raising=False)
    monkeypatch.setattr(
        gen._llm,
        "complete_json",
        lambda *a, **k: _ret(
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
    monkeypatch.setattr(gen, "_capture_spec_decision", lambda *a, **k: _ret(None), raising=False)

    # Run 1
    await gen.from_request_with_team("rebuild importer", "product:platform", event_callback=_on_event)
    run_1_ids = {ev.get("build_run_id") for ev in captured}
    assert len(run_1_ids) == 1, f"build_run_id must be uniform within a run; got {run_1_ids}"
    assert next(iter(run_1_ids)), "build_run_id must be non-empty"
    run_1_id = next(iter(run_1_ids))

    # Run 2 — distinct id
    captured.clear()
    await gen.from_request_with_team("rebuild importer", "product:platform", event_callback=_on_event)
    run_2_id = next(iter({ev.get("build_run_id") for ev in captured}))
    assert run_2_id != run_1_id, "distinct from_request_with_team calls must generate distinct build_run_ids"


@pytest.mark.integration
async def test_build_team_resolved_fires_after_resolve_lenses(monkeypatch):
    """build.team_resolved must fire once, with {build_run_id, lenses}, after lens
    resolution and BEFORE any agent.phase events."""
    from core.engine.orchestration.deep_committee import CommitteeResult
    from core.engine.product import spec_generator as sg

    captured: list[tuple[str, dict]] = []

    async def _on_event(event_type, payload):
        captured.append((event_type, payload))

    async def _fake_committee(*args, **kwargs):
        cb = kwargs.get("event_callback")
        if cb is not None:
            # Phase event fires AFTER team_resolved must have already fired
            await cb(
                "agent.phase.end",
                {
                    "lens": "architecture",
                    "phase_idx": 0,
                    "cognitive_function": "frame",
                    "confidence": 0.9,
                },
            )
        return CommitteeResult(lens_outputs={"architecture": "a"}, lens_lineage={}, synthesis="syn")

    async def _ret(v):
        return v

    monkeypatch.setattr(
        sg, "classify_task", lambda *a, **k: _ret({"discipline": "architecture", "specialties": ["security-x"]})
    )
    monkeypatch.setattr(sg, "resolve_lenses", lambda c: ["architecture", "security"])
    monkeypatch.setattr(sg, "score_lens_composition", _async_ret(ScoredLensComposition()))
    monkeypatch.setattr(sg, "run_deep_committee", _fake_committee)

    gen = sg.SpecGenerator(db_pool=None)
    monkeypatch.setattr(
        gen,
        "_gather_build_context",
        lambda *a, **k: _ret(
            {"health": {}, "vision": None, "tech_context": {}, "related_files": [], "prior_decisions": []}
        ),
        raising=False,
    )
    monkeypatch.setattr(gen, "_assess_risk", lambda *a, **k: _ret({"risk": "", "blast_radius": {}}), raising=False)
    monkeypatch.setattr(
        gen._llm,
        "complete_json",
        lambda *a, **k: _ret(
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
    monkeypatch.setattr(gen, "_capture_spec_decision", lambda *a, **k: _ret(None), raising=False)

    await gen.from_request_with_team("rebuild", "product:platform", event_callback=_on_event)

    # Find the team_resolved event
    team_resolved = [(t, p) for t, p in captured if t == "build.team_resolved"]
    assert len(team_resolved) == 1, f"build.team_resolved must fire exactly once; got {len(team_resolved)}"
    _, payload = team_resolved[0]
    assert payload["lenses"] == ["architecture", "security"]
    assert payload["build_run_id"]  # non-empty

    # Order: team_resolved must come BEFORE any agent.phase event
    types_in_order = [t for t, _ in captured]
    team_idx = types_in_order.index("build.team_resolved")
    phase_idx = next((i for i, t in enumerate(types_in_order) if t.startswith("agent.phase.")), None)
    if phase_idx is not None:
        assert team_idx < phase_idx, "build.team_resolved must fire BEFORE agent.phase events"


@pytest.mark.integration
async def test_agent_phase_start_fires_per_phase(monkeypatch):
    """The deep committee's _on_phase closure must emit BOTH start AND end events
    for each phase, both carrying the lens carrier."""
    from core.engine.cognition.reasoning_run import ReasoningResult
    from core.engine.orchestration import deep_committee as dc

    events: list[tuple[str, dict]] = []

    async def _on_event(event_type, payload):
        events.append((event_type, payload))

    async def _fake_run_reasoning(*, thought, classification, composition, product_id, model, on_phase):
        # Simulate two phases — invoke on_phase BEFORE AND AFTER each (the implementation
        # will emit start before calling the phase work and end after).
        if on_phase is not None:
            # Phase 1 start + end
            await on_phase(0, 2, "frame", None, None, [])  # start (output=None, confidence=None)
            await on_phase(0, 2, "frame", "framed", 0.9, [])  # end
            # Phase 2 start + end
            await on_phase(1, 2, "assess", None, None, [])
            await on_phase(1, 2, "assess", "assessed", 0.8, [])
        return ReasoningResult(conclusion="ok", phases=[])

    async def _fake_compose(classification, product_id):
        from core.engine.cognition.models import CognitiveComposition, RecipePhase

        return CognitiveComposition(
            meta_skills=[classification["discipline"]],
            depth=3,
            active_phases=[RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")],
            resolved_instruments={},
            prompt_sections=[],
            fusion_mode=False,
        )

    monkeypatch.setattr(dc, "run_reasoning", _fake_run_reasoning)
    monkeypatch.setattr(dc, "_compose_for_lens", _fake_compose, raising=False)

    await dc.run_deep_committee("rebuild", ["architecture"], "product:platform", event_callback=_on_event)

    # We should see two start + two end events for the single lens
    starts = [(t, p) for t, p in events if t == "agent.phase.start"]
    ends = [(t, p) for t, p in events if t == "agent.phase.end"]
    assert len(starts) == 2, f"expected 2 phase.start events; got {len(starts)}"
    assert len(ends) == 2, f"expected 2 phase.end events; got {len(ends)}"
    # All carry the lens
    for _, p in starts + ends:
        assert p["lens"] == "architecture"
