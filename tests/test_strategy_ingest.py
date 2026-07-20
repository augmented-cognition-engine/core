from __future__ import annotations


def test_roadmap_item_defaults_kind_gap_backward_compat():
    from core.engine.product.roadmap_models import RoadmapItem

    # Existing callers construct without kind/source_ref → must default to "gap".
    item = RoadmapItem(title="cap.dim", pillar="", discipline="dim")
    assert item.kind == "gap"
    assert item.source_ref is None

    phase = RoadmapItem(
        title="Phase 3", pillar="", discipline=None, kind="phase", source_ref="ace-world-class-roadmap.md"
    )
    assert phase.kind == "phase"
    assert phase.source_ref == "ace-world-class-roadmap.md"


def test_ingest_phase_upserts_not_duplicates():
    import asyncio

    class FakeDB:
        def __init__(self):
            self.calls = []
            self.existing = []

        async def query(self, q, params=None):
            self.calls.append(q.strip().split()[0].upper())  # verb: SELECT/UPDATE/CREATE
            if q.strip().upper().startswith("SELECT"):
                return self.existing
            if q.strip().upper().startswith("CREATE"):
                self.existing = [{"id": "roadmap_phase:abc"}]  # now it "exists"
            return [{"id": "roadmap_phase:abc"}]

    class FakePool:
        def __init__(self, db):
            self._db = db

        def connection(self):
            db = self._db

            class Ctx:
                async def __aenter__(self):
                    return db

                async def __aexit__(self, *a):
                    return False

            return Ctx()

    from core.engine.product.strategy_ingest import ingest_phase

    db = FakeDB()
    pool = FakePool(db)
    asyncio.run(
        ingest_phase(
            "Phase 1", 1, "active", "p1 summary", "ace-world-class-roadmap.md", None, "product:platform", pool=pool
        )
    )
    asyncio.run(
        ingest_phase(
            "Phase 1", 1, "active", "p1 summary", "ace-world-class-roadmap.md", None, "product:platform", pool=pool
        )
    )
    # First call: SELECT (miss) + CREATE. Second: SELECT (hit) + UPDATE. Never two CREATEs.
    assert db.calls.count("CREATE") == 1
    assert db.calls.count("UPDATE") == 1


def test_ingest_spec_dedup_updates_status_and_accumulates_source():
    import asyncio

    from core.engine.product.strategy_ingest import ingest_spec

    class FakeDB:
        def __init__(self):
            self.rows = []
            self.last_update = None

        async def query(self, q, params=None):
            u = q.strip().upper()
            if u.startswith("SELECT"):
                # Only the agent_spec lookup returns the stored row; others (phase/capability) miss.
                if "FROM AGENT_SPEC" in u:
                    return self.rows
                return []
            if u.startswith("CREATE"):
                self.rows = [{"id": "agent_spec:x", "source_ref": params.get("source_ref", [])}]
                return self.rows
            if u.startswith("UPDATE"):
                self.last_update = params
                return [{"id": "agent_spec:x"}]
            return []

    class FakePool:
        def __init__(self, db):
            self._db = db

        def connection(self):
            db = self._db

            class Ctx:
                async def __aenter__(self):
                    return db

                async def __aexit__(self, *a):
                    return False

            return Ctx()

    db = FakeDB()
    pool = FakePool(db)
    # First: from the matrix (draft, source A). Second: from a plan (shipped, source B).
    asyncio.run(
        ingest_spec(
            "Cognify extraction",
            "draft",
            "high",
            2,
            None,
            ["ace-adopt-priority-matrix.md"],
            None,
            "product:platform",
            pool=pool,
        )
    )
    asyncio.run(
        ingest_spec(
            "Cognify extraction",
            "shipped",
            "high",
            2,
            None,
            ["2026-06-19-graph-tensions.md"],
            None,
            "product:platform",
            pool=pool,
        )
    )
    # Second call must UPDATE (dedup), set status=shipped, and union both source_refs.
    assert db.last_update is not None
    assert db.last_update["status"] == "shipped"
    assert set(db.last_update["source_ref"]) == {"ace-adopt-priority-matrix.md", "2026-06-19-graph-tensions.md"}


def test_ingest_spec_status_monotonic_protects_done_work():
    """Re-ingest is status-monotonic: a live-shipped spec must NOT revert to draft when the source
    doc still lists it draft (the exact arm-drift bug). Not-done specs still advance from the doc."""
    import asyncio

    from core.engine.product.strategy_ingest import ingest_spec

    class FakeDB:
        def __init__(self, live_status):
            self.row = {"id": "agent_spec:x", "source_ref": [], "status": live_status}
            self.last_update = None

        async def query(self, q, params=None):
            u = q.strip().upper()
            if u.startswith("SELECT"):
                return [self.row] if "FROM AGENT_SPEC" in u else []
            if u.startswith("UPDATE"):
                self.last_update = params
                return [{"id": "agent_spec:x"}]
            return []

    class FakePool:
        def __init__(self, db):
            self._db = db

        def connection(self):
            db = self._db

            class Ctx:
                async def __aenter__(self):
                    return db

                async def __aexit__(self, *a):
                    return False

            return Ctx()

    # done/in-progress/human statuses are PRESERVED even when the doc still says draft —
    # re-ingest must never regress real loop or human progress.
    for live in ("shipped", "built", "completed", "verifying", "executing", "blocked", "superseded", "failed"):
        db = FakeDB(live)
        asyncio.run(
            ingest_spec(
                "Design arm",
                "draft",
                "medium",
                4,
                None,
                ["ace-adopt-priority-matrix.md"],
                None,
                "product:platform",
                pool=FakePool(db),
            )
        )
        assert db.last_update["status"] == live, f"re-ingest must not regress live={live} to draft"

    # pre-work statuses (draft/approved/None) — the doc still drives them
    for live, doc, expect in (
        ("draft", "approved", "approved"),
        ("approved", "draft", "draft"),
        (None, "approved", "approved"),
    ):
        db = FakeDB(live)
        asyncio.run(
            ingest_spec(
                "Eval harness",
                doc,
                "high",
                1,
                None,
                ["ace-adopt-priority-matrix.md"],
                None,
                "product:platform",
                pool=FakePool(db),
            )
        )
        assert db.last_update["status"] == expect, f"doc must drive pre-work live={live} -> {expect}"


def test_ingest_decision_skips_when_title_exists(monkeypatch):
    import asyncio

    import core.engine.product.strategy_ingest as si

    created = []

    async def fake_create_decision(**kwargs):
        created.append(kwargs["title"])
        return {"id": "decision:new"}

    # find_existing returns a hit for the north-star title (already captured).
    async def fake_find(title, product_id, pool=None):
        return "decision:existing" if title == "ACE identity" else None

    monkeypatch.setattr(si, "create_decision", fake_create_decision)
    monkeypatch.setattr(si, "_find_decision_by_title", fake_find)

    asyncio.run(
        si.ingest_decision("ACE identity", "body", "direction", None, "ace-north-star.md", None, "product:platform")
    )
    asyncio.run(
        si.ingest_decision(
            "Build is the purpose", "body", "direction", None, "ace-north-star.md", None, "product:platform"
        )
    )
    # Existing title skipped; new title created.
    assert created == ["Build is the purpose"]


def test_seed_session_strategy_counts(monkeypatch):
    import asyncio

    import core.engine.product.strategy_ingest as si

    calls = {"phase": 0, "spec": 0, "decision": 0, "edge": 0}

    async def fphase(*a, **k):
        calls["phase"] += 1
        return "roadmap_phase:%d" % calls["phase"]

    async def fspec(*a, **k):
        calls["spec"] += 1
        return "agent_spec:%d" % calls["spec"]

    async def fdec(title, *a, **k):
        calls["decision"] += 1
        return "decision:" + title[:4]

    async def fedge(*a, **k):
        calls["edge"] += 1
        return {"id": "supersedes:1"}

    monkeypatch.setattr(si, "ingest_phase", fphase)
    monkeypatch.setattr(si, "ingest_spec", fspec)
    monkeypatch.setattr(si, "ingest_decision", fdec)
    monkeypatch.setattr(si, "create_edge", fedge)

    summary = asyncio.run(si.seed_session_strategy("product:platform"))
    from core.engine.product import strategy_seed_data as d

    assert summary["phases"] == len(d.PHASES)
    assert summary["specs"] == len(d.SPECS)
    assert summary["decisions"] == len(d.DECISIONS) + len(d.REJECTIONS)
    assert summary["supersedes"] == len(d.SUPERSEDES)


def test_intent_first_tiering_and_lane_mapping():
    from core.engine.product.roadmap import _lane_for_strategy_item, _tier
    from core.engine.product.roadmap_models import RoadmapItem

    gap = RoadmapItem(title="cap.dim", pillar="", discipline="dim", rank=0.9, kind="gap")
    spec = RoadmapItem(title="Code arm", pillar="", discipline=None, rank=0.5, kind="spec")
    phase = RoadmapItem(title="Phase 3", pillar="", discipline=None, rank=0.1, kind="phase")

    # Tier: phase(2) > spec(1) > gap(0). A low-rank phase still outranks a high-rank gap.
    assert _tier(phase) > _tier(spec) > _tier(gap)
    ordered = sorted([gap, spec, phase], key=lambda i: (_tier(i), i.rank), reverse=True)
    assert [i.kind for i in ordered] == ["phase", "spec", "gap"]

    # Lane mapping for strategy items.
    assert _lane_for_strategy_item("spec", "shipped") == "done"
    assert _lane_for_strategy_item("spec", "building") == "now"
    assert _lane_for_strategy_item("spec", "approved") == "next"
    assert _lane_for_strategy_item("spec", "blocked") == "blocked"
    assert _lane_for_strategy_item("spec", "superseded") == "parked"
    assert _lane_for_strategy_item("phase", "active") == "now"
    assert _lane_for_strategy_item("phase", "next") == "next"
    assert _lane_for_strategy_item("phase", "done") == "done"


def test_ace_roadmap_item_serialization_includes_kind():
    from core.engine.mcp.tools import _roadmap_item_to_dict  # helper extracted in Step 3
    from core.engine.product.roadmap_models import RoadmapItem

    d = _roadmap_item_to_dict(
        RoadmapItem(
            title="Phase 3",
            pillar="",
            discipline=None,
            kind="phase",
            source_ref="ace-world-class-roadmap.md",
            lane="next",
            rank=2.9,
        )
    )
    assert d["kind"] == "phase"
    assert d["source_ref"] == "ace-world-class-roadmap.md"
    assert d["title"] == "Phase 3"


def test_gap_floor_keeps_gaps_when_strategy_exceeds_cap():
    """Honor 'both, intent-first': decided work leads, but the top gaps still
    surface below it (reserved floor) instead of being starved by the cap."""
    from core.engine.product.roadmap import _GAP_FLOOR, _merge_intent_first
    from core.engine.product.roadmap_models import RoadmapItem

    strategy = [RoadmapItem(title=f"S{i}", pillar="", discipline=None, kind="spec", rank=1.5) for i in range(30)]
    gaps = [RoadmapItem(title=f"G{i}", pillar="", discipline="d", kind="gap", rank=0.9) for i in range(20)]

    merged = _merge_intent_first(strategy, gaps, max_items=25)

    assert len(merged) == 25
    kinds = [m.kind for m in merged]
    assert kinds[0] == "spec"  # decided work leads
    assert sum(1 for k in kinds if k == "gap") == _GAP_FLOOR  # gaps not starved
    assert sum(1 for k in kinds if k == "spec") == 25 - _GAP_FLOOR


def test_merge_intent_first_no_gaps_is_strategy_only():
    """No gaps + fewer strategy than cap → all strategy, no padding, no error."""
    from core.engine.product.roadmap import _merge_intent_first
    from core.engine.product.roadmap_models import RoadmapItem

    strategy = [RoadmapItem(title=f"S{i}", pillar="", discipline=None, kind="spec", rank=1.5) for i in range(3)]
    merged = _merge_intent_first(strategy, [], max_items=25)
    assert [m.title for m in merged] == ["S0", "S1", "S2"]
