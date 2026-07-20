# tests/test_capability_mapper.py
"""Tests for CapabilityMapper — bootstrap from graph, incremental mapping with glob patterns."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_pool(mock_db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.fixture
def mapper(mock_pool):
    from core.engine.product.capability_mapper import CapabilityMapper

    return CapabilityMapper(mock_pool)


# ---------------------------------------------------------------------------
# test_glob_matching
# ---------------------------------------------------------------------------


def test_glob_matching(mapper):
    """_matches_glob handles ** recursive patterns and fnmatch patterns."""
    # ** pattern: prefix-based matching
    assert mapper._matches_glob("engine/auth/login.py", "engine/auth/**") is True
    assert mapper._matches_glob("engine/auth/utils/helpers.py", "engine/auth/**") is True
    assert mapper._matches_glob("engine/billing/invoice.py", "engine/auth/**") is False

    # Non-** fnmatch pattern
    assert mapper._matches_glob("engine/auth/login.py", "engine/auth/*.py") is True
    assert mapper._matches_glob("engine/auth/login.ts", "engine/auth/*.py") is False

    # Edge: pattern with no wildcard
    assert mapper._matches_glob("engine/auth/login.py", "engine/auth/login.py") is True
    assert mapper._matches_glob("engine/auth/other.py", "engine/auth/login.py") is False


def test_matches_glob_normalizes_core_prefix(mapper):
    """Current code lives at core/engine/...; the fallback globs are written engine/...
    A leading core/ must be normalized so the globs match the canonical generation (item E)."""
    assert mapper._matches_glob("core/engine/auth/login.py", "engine/auth/**") is True
    assert mapper._matches_glob("core/engine/auth/login.py", "engine/auth/*.py") is True
    # the bare (stale) form still matches too — normalization is additive, not a swap
    assert mapper._matches_glob("engine/auth/login.py", "engine/auth/**") is True
    # a non-core path is unaffected
    assert mapper._matches_glob("portal/src/App.tsx", "portal/src/**") is True


# ---------------------------------------------------------------------------
# test_incremental_map_glob_match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_incremental_map_glob_match(mock_pool, mock_db):
    """New files matching existing capability globs get auto-mapped via RELATE."""
    from core.engine.product.capability_mapper import CapabilityMapper

    mapper = CapabilityMapper(mock_pool)

    # Realizes edges with glob patterns
    realizes_rows = [
        {"capability": "capability:auth", "file_glob": "engine/auth/**"},
    ]

    mock_db.query = AsyncMock(
        side_effect=[
            realizes_rows,  # SELECT realizes edges (glob patterns)
            [],  # RELATE for matched file
        ]
    )

    new_files = [
        {"id": "graph_file:f1", "path": "engine/auth/login.py"},
        {"id": "graph_file:f2", "path": "engine/billing/invoice.py"},
    ]

    result = await mapper.incremental_map(new_files, "product:test")

    assert result["mapped"] == 1
    assert result["unmapped"] == 1


# ---------------------------------------------------------------------------
# test_propose_capabilities_returns_proposals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_capabilities_returns_proposals(mapper):
    """propose_capabilities calls LLM and returns structured proposal list."""
    files = [
        {"id": "graph_file:f1", "path": "engine/auth/login.py", "language": "python"},
        {"id": "graph_file:f2", "path": "engine/auth/signup.py", "language": "python"},
        {"id": "graph_file:f3", "path": "engine/billing/invoice.py", "language": "python"},
    ]
    decisions = [
        {"id": "graph_decision:d1", "title": "Use JWT for auth", "description": "Chose JWT"},
    ]

    llm_response = [
        {
            "name": "Authentication",
            "slug": "auth",
            "description": "User login and signup flows",
            "file_glob": "engine/auth/**",
            "file_ids": ["graph_file:f1", "graph_file:f2"],
            "confidence": 0.9,
        },
        {
            "name": "Billing",
            "slug": "billing",
            "description": "Invoice management",
            "file_glob": "engine/billing/**",
            "file_ids": ["graph_file:f3"],
            "confidence": 0.85,
        },
    ]

    with patch.object(mapper, "_llm_propose", new=AsyncMock(return_value=llm_response)):
        proposals = await mapper.propose_capabilities(files, decisions)

    assert len(proposals) == 2
    assert proposals[0]["slug"] == "auth"
    assert proposals[0]["confidence"] == 0.9
    assert proposals[1]["slug"] == "billing"
    assert "file_glob" in proposals[0]
    assert "file_ids" in proposals[0]


# ---------------------------------------------------------------------------
# test_bootstrap_creates_scan_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_creates_scan_record(mock_pool, mock_db):
    """bootstrap_from_graph creates a capability_scan record and updates it on completion."""
    from core.engine.product.capability_mapper import CapabilityMapper

    mapper = CapabilityMapper(mock_pool)

    scan_record = {"id": "capability_scan:s1", "status": "running", "product": "product:test"}
    files = [
        {"id": "graph_file:f1", "path": "engine/auth/login.py", "language": "python"},
    ]
    decisions = [
        {"id": "graph_decision:d1", "title": "Use JWT", "description": "JWT for auth"},
    ]
    llm_proposals = [
        {
            "name": "Authentication",
            "slug": "auth",
            "description": "Auth flows",
            "file_glob": "engine/auth/**",
            "file_ids": ["graph_file:f1"],
            "confidence": 0.9,
        }
    ]

    mock_db.query = AsyncMock(
        side_effect=[
            [scan_record],  # CREATE capability_scan (status: running)
            [],  # SELECT graph (lookup graph_id for product — none found)
            files,  # SELECT graph_file (fallback: all files)
            decisions,  # SELECT graph_decision
            [{"id": "capability_scan:s1", "status": "completed"}],  # UPDATE scan
        ]
    )

    with patch.object(mapper, "_llm_propose", new=AsyncMock(return_value=llm_proposals)):
        proposals = await mapper.bootstrap_from_graph("product:test")

    # Proposals returned (not auto-committed)
    assert len(proposals) == 1
    assert proposals[0]["slug"] == "auth"

    # Verify DB was called: CREATE + SELECT graph + SELECT files + SELECT decisions + UPDATE
    assert mock_db.query.call_count == 5

    # First call must CREATE the scan record with status=running
    first_sql = mock_db.query.call_args_list[0][0][0].upper()
    assert "CREATE" in first_sql or "INSERT" in first_sql
    assert "CAPABILITY_SCAN" in first_sql

    # Last call must UPDATE the scan record with status=completed
    last_sql = mock_db.query.call_args_list[4][0][0].upper()
    assert "UPDATE" in last_sql
    assert "COMPLETED" in last_sql or "STATUS" in last_sql


# ---------------------------------------------------------------------------
# map_files_to_capabilities — the deterministic realizes-edge backfill.
# Regression coverage for the dropped-SQL bug (commit 3e7260319) that left
# `db.query({"product": product_id})` with no query string → caps=[] → 0 edges
# → blind capability audit. See docs/superpowers/specs/2026-06-22-capability-
# mapping-blind-audit-fix.md.
# ---------------------------------------------------------------------------


class _RecordingDB:
    """Content-dispatching fake: returns rows by SQL shape, records every call.

    Robust to the variable query count of map_files_to_capabilities (depends on
    how many files match), unlike a fixed side_effect list. A non-str query
    (the dropped-SQL bug calls db.query(<dict>)) returns [] — i.e. caps=[].
    """

    def __init__(self, caps, files, test_files=None):
        self.caps = caps
        self.files = files
        self.test_files = test_files or []
        self.queries: list = []  # (sql, params)

    async def query(self, sql, params=None):
        self.queries.append((sql, params))
        if not isinstance(sql, str):  # the bug: db.query(<params dict>) — no SQL
            return []
        u = sql.upper()
        if u.startswith("SELECT") and "FROM CAPABILITY " in u + " ":
            return list(self.caps)
        if "TESTS/TEST_" in u:  # test-file index query (check before generic graph_file)
            return list(self.test_files)
        if u.startswith("SELECT") and "FROM GRAPH_FILE" in u:
            return list(self.files)
        if u.startswith("SELECT REALITY"):
            return [{"reality": None}]
        return []  # RELATE / DELETE / UPDATE


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


@pytest.mark.asyncio
async def test_map_files_loads_caps_with_real_select():
    """The capability load must be a real SQL string, not a bare params dict.

    Fails on the dropped-SQL bug where db.query is called with only {"product": ...}.
    """
    from core.engine.product.capability_mapper import CapabilityMapper

    db = _RecordingDB(caps=[], files=[])
    mapper = CapabilityMapper(_FakePool(db))
    await mapper.map_files_to_capabilities("product:platform")

    assert db.queries, "no queries issued"
    first_sql = db.queries[0][0]
    assert isinstance(first_sql, str), "caps load is not a SQL string (the dropped-SQL bug)"
    assert "FROM capability" in first_sql
    assert "product" in first_sql.lower(), "caps must be filtered by product"


@pytest.mark.asyncio
async def test_map_files_maps_with_fallback_glob():
    """A capability with no file_glob still maps files via _SLUG_GLOB_FALLBACKS.

    Fails on the bug: caps=[] → cap_globs=[] → mapped=0 regardless of the fallbacks.
    """
    from core.engine.product.capability_mapper import CapabilityMapper

    caps = [{"id": "capability:cap1", "slug": "capture_pipeline", "file_glob": None}]
    files = [
        {"id": "graph_file:f1", "path": "core/engine/capture/atomic.py"},  # matches engine/capture/** via core/ norm
        {"id": "graph_file:f2", "path": "core/engine/billing/x.py"},  # no match
    ]
    db = _RecordingDB(caps=caps, files=files)
    mapper = CapabilityMapper(_FakePool(db))

    result = await mapper.map_files_to_capabilities("product:platform")

    assert result["mapped"] >= 1, "fallback-glob capability mapped no files"
    relates = [q for q, _ in db.queries if isinstance(q, str) and "RELATE" in q.upper()]
    assert any("capability:cap1" in q for q in relates), "no realizes edge created for matched cap"


@pytest.mark.asyncio
async def test_map_files_clears_prior_backfill_edges_before_relate():
    """The full bootstrap is idempotent: it clears prior source='backfill' edges
    before re-RELATE, so a re-bootstrap (scanner stale-edge path) never piles up dupes."""
    from core.engine.product.capability_mapper import CapabilityMapper

    caps = [{"id": "capability:cap1", "slug": "capture_pipeline", "file_glob": None}]
    files = [{"id": "graph_file:f1", "path": "core/engine/capture/atomic.py"}]
    db = _RecordingDB(caps=caps, files=files)
    mapper = CapabilityMapper(_FakePool(db))

    await mapper.map_files_to_capabilities("product:platform")

    sqls = [q for q, _ in db.queries if isinstance(q, str)]
    delete_idx = next((i for i, q in enumerate(sqls) if "DELETE" in q.upper() and "REALIZES" in q.upper()), None)
    relate_idx = next((i for i, q in enumerate(sqls) if "RELATE" in q.upper()), None)
    assert delete_idx is not None, "no idempotency DELETE of prior backfill edges"
    assert relate_idx is not None, "no RELATE issued"
    assert delete_idx < relate_idx, "DELETE must precede RELATE (clear-then-rebuild)"
    # The DELETE must be product-scoped, or bootstrapping one product wipes another's edges.
    delete_sql = sqls[delete_idx].lower()
    assert "out.product" in delete_sql, "DELETE must be product-scoped (out.product), not global"


@pytest.mark.asyncio
async def test_backfill_dedups_stale_generation_by_canonical_path():
    """The graph carried two generations (engine/x AND core/engine/x). The backfill must map each
    LOGICAL file once, preferring the canonical core/ record — not RELATE the same logical file
    twice (item E)."""
    from core.engine.product.capability_mapper import CapabilityMapper

    caps = [{"id": "capability:cap1", "slug": "capture_pipeline", "file_glob": None}]
    files = [
        {"id": "graph_file:stale", "path": "engine/capture/atomic.py"},  # stale generation
        {"id": "graph_file:current", "path": "core/engine/capture/atomic.py"},  # canonical twin
    ]
    db = _RecordingDB(caps=caps, files=files)
    mapper = CapabilityMapper(_FakePool(db))

    result = await mapper.map_files_to_capabilities("product:platform")

    relates = [q for q, _ in db.queries if isinstance(q, str) and "RELATE" in q.upper()]
    # exactly one realizes edge for the logical file, and it's the canonical (core/) record
    assert len(relates) == 1, f"expected 1 deduped RELATE, got {len(relates)}: {relates}"
    assert "graph_file:current" in relates[0], "must keep the canonical core/ record, not the stale twin"
    assert result["mapped"] == 1


@pytest.mark.asyncio
async def test_strategic_capability_globs_resolve():
    """The 5 kebab-case strategic capabilities must carry fallback globs so they stop showing as
    phantom 0.00 gaps. Verified via the backfill: each maps its real code home (item E)."""
    from core.engine.product.capability_mapper import CapabilityMapper

    cases = [
        ("closed-loop-learning", "core/engine/arms/strategy/depth_scorer.py"),
        ("intelligence-routing", "core/engine/orchestrator/classifier.py"),
        ("onboarding-flow", "core/engine/onboarding/conversation.py"),
        ("partner-voice", "core/engine/voice/surfaces.py"),
        ("substrate-quality", "core/engine/sentinel/engines/roadmap_reconciler.py"),
    ]
    for slug, path in cases:
        caps = [{"id": f"capability:{slug}", "slug": slug, "file_glob": None}]
        files = [{"id": "graph_file:f", "path": path}]
        db = _RecordingDB(caps=caps, files=files)
        mapper = CapabilityMapper(_FakePool(db))
        result = await mapper.map_files_to_capabilities("product:platform")
        assert result["mapped"] == 1, f"{slug} did not map its code home {path}"
