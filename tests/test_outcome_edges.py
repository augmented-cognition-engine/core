"""Tests for capture_outcome's afferent backward-flow edges (item D).

When an arm build is recorded, the action_outcome node must edge back into the graph so the loop is
traversable: outcome_addresses->spec, outcome_exercises->capability, outcome_touches->graph_file. All idempotent (create_edge
dedups), non-fatal, capped. See docs/superpowers/specs/2026-06-22-afferent-backward-flow-edges-design.md.
"""

from __future__ import annotations

import pytest

# --- fakes -----------------------------------------------------------------


class _FakeWS:
    branch = "arm/x-1"
    path = "/w"
    repo_root = "/r"

    def __init__(self, changed=None):
        self._changed = changed if changed is not None else ["engine/a.py", "engine/b.py"]

    def diff(self):
        return "some diff"

    def changed_files(self):
        return list(self._changed)


class _FakePlan:
    profile = None
    pipeline = ["ground_scan", "generate"]


class _FakeResult:
    def __init__(self, changed=None):
        self.workspace = _FakeWS(changed)
        self.plan = _FakePlan()
        self.performed = []


class _FakeSolution:
    def __init__(self, spec_id="agent_spec:s1"):
        self.spec_id = spec_id
        self.intent = "do the thing"


class _FakeVerdict:
    def __init__(self, passed=True):
        self.passed = passed
        self.reason = "ok" if passed else "nope"


class _FakeDB:
    """Content-dispatching fake. Returns an outcome id for CREATE, a capability for the spec lookup,
    and a graph_file row for path lookups (unless the path is in `unresolvable`)."""

    def __init__(self, capability="capability:c1", unresolvable=()):
        self._capability = capability
        self._unresolvable = set(unresolvable)
        self.queries: list = []

    async def query(self, sql, params=None):
        self.queries.append((sql, params))
        u = sql.upper()
        if u.startswith("CREATE ACTION_OUTCOME"):
            return [{"id": "action_outcome:o1"}]
        if u.startswith("SELECT CAPABILITY FROM"):
            return [{"capability": self._capability}] if self._capability else [{"capability": None}]
        if "FROM GRAPH_FILE" in u:
            path = (params or {}).get("path")
            return [] if path in self._unresolvable else [{"id": f"graph_file:{abs(hash(path)) % 999}"}]
        return []


class _FakePool:
    def __init__(self, db):
        self._db = db

    def connection(self):
        db = self._db

        class _Ctx:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def _patch_edges(monkeypatch):
    """Record every create_edge call; return the recording list."""
    import core.engine.arms.outcome as outcome

    calls: list = []

    async def fake_create_edge(edge_type, from_id, to_id, metadata=None, pool=None):
        calls.append({"type": edge_type, "from": from_id, "to": to_id, "meta": metadata})
        return {"id": f"{edge_type}:e"}

    monkeypatch.setattr(outcome, "create_edge", fake_create_edge)
    return calls


# --- tests -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_addresses_edge_created_for_spec(monkeypatch):
    import core.engine.arms.outcome as outcome

    calls = _patch_edges(monkeypatch)
    db = _FakeDB()
    await outcome.capture_outcome(
        _FakeSolution(), "code", _FakeResult(), _FakeVerdict(), product_id="product:platform", pool=_FakePool(db)
    )
    addresses = [c for c in calls if c["type"] == "outcome_addresses"]
    assert len(addresses) == 1
    assert addresses[0]["from"] == "action_outcome:o1"
    assert addresses[0]["to"] == "agent_spec:s1"


@pytest.mark.asyncio
async def test_exercises_edge_from_spec_capability(monkeypatch):
    import core.engine.arms.outcome as outcome

    calls = _patch_edges(monkeypatch)
    db = _FakeDB(capability="capability:c1")
    await outcome.capture_outcome(
        _FakeSolution(), "code", _FakeResult(), _FakeVerdict(), product_id="product:platform", pool=_FakePool(db)
    )
    exercises = [c for c in calls if c["type"] == "outcome_exercises"]
    assert len(exercises) == 1
    assert exercises[0]["from"] == "action_outcome:o1"
    assert exercises[0]["to"] == "capability:c1"


@pytest.mark.asyncio
async def test_no_spec_no_spec_or_cap_edges(monkeypatch):
    import core.engine.arms.outcome as outcome

    calls = _patch_edges(monkeypatch)
    db = _FakeDB()
    sol = _FakeSolution(spec_id=None)
    await outcome.capture_outcome(
        sol, "code", _FakeResult(), _FakeVerdict(), product_id="product:platform", pool=_FakePool(db)
    )
    assert not any(c["type"] in ("outcome_addresses", "outcome_exercises") for c in calls)


@pytest.mark.asyncio
async def test_touches_edges_for_changed_files(monkeypatch):
    import core.engine.arms.outcome as outcome

    calls = _patch_edges(monkeypatch)
    # one path resolves, one does not -> exactly one touches edge
    db = _FakeDB(unresolvable={"engine/b.py"})
    await outcome.capture_outcome(
        _FakeSolution(),
        "code",
        _FakeResult(changed=["engine/a.py", "engine/b.py"]),
        _FakeVerdict(),
        product_id="product:platform",
        pool=_FakePool(db),
    )
    touches = [c for c in calls if c["type"] == "outcome_touches"]
    assert len(touches) == 1
    assert touches[0]["from"] == "action_outcome:o1"


@pytest.mark.asyncio
async def test_touches_capped(monkeypatch):
    import core.engine.arms.outcome as outcome

    calls = _patch_edges(monkeypatch)
    many = [f"engine/f{i}.py" for i in range(outcome._MAX_TOUCH + 20)]
    db = _FakeDB()
    await outcome.capture_outcome(
        _FakeSolution(),
        "code",
        _FakeResult(changed=many),
        _FakeVerdict(),
        product_id="product:platform",
        pool=_FakePool(db),
    )
    touches = [c for c in calls if c["type"] == "outcome_touches"]
    assert len(touches) == outcome._MAX_TOUCH


@pytest.mark.asyncio
async def test_edge_failure_is_non_fatal(monkeypatch):
    import core.engine.arms.outcome as outcome

    async def boom(*a, **k):
        raise RuntimeError("edge down")

    monkeypatch.setattr(outcome, "create_edge", boom)
    db = _FakeDB()
    # must not raise
    await outcome.capture_outcome(
        _FakeSolution(), "code", _FakeResult(), _FakeVerdict(), product_id="product:platform", pool=_FakePool(db)
    )


@pytest.mark.asyncio
async def test_failed_build_still_edges_with_passed_false(monkeypatch):
    """A failed build still addressed a spec + touched files — edges are created with passed=False."""
    import core.engine.arms.outcome as outcome

    calls = _patch_edges(monkeypatch)
    db = _FakeDB()
    await outcome.capture_outcome(
        _FakeSolution(),
        "code",
        _FakeResult(),
        _FakeVerdict(passed=False),
        product_id="product:platform",
        pool=_FakePool(db),
    )
    addresses = [c for c in calls if c["type"] == "outcome_addresses"]
    assert len(addresses) == 1
    # parked rides alongside passed so a traversal counting "failed attempts at this spec" can
    # exclude runs the ENVIRONMENT killed — those are evidence of nothing.
    assert addresses[0]["meta"] == {"passed": False, "parked": False}
