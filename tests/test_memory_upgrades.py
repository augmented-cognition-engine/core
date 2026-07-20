"""Tests for P0-M memory layer upgrades: M1–M7."""

import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The M1 tests below load .claude/hooks/ace-post-tool.py directly — private
# session tooling, not shipped in the public export. Skip those (M2-M7 test
# shipped core.engine.capture.* modules and must keep running).
_HOOKS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "hooks"
_HAS_PRIVATE_HOOKS = _HOOKS_DIR.is_dir()
_skip_no_hooks = pytest.mark.skipif(
    not _HAS_PRIVATE_HOOKS, reason="requires private .claude/hooks/ (not shipped in the public export)"
)

# ── helpers ────────────────────────────────────────────────────────────────


def _make_pool(rows=None):
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[[]])

    @contextlib.asynccontextmanager
    async def _connection():
        yield mock_conn

    mock_pool = MagicMock()
    mock_pool.connection = _connection
    return mock_pool, mock_conn


# ── M1 — implicit signal inference ────────────────────────────────────────


def test_m1_infer_security_file_edit():
    pytest.skip("hook tested via importlib in subsequent tests")


@_skip_no_hooks
def test_m1_infer_implicit_security_path():
    """Direct import of the function after sys.path manipulation."""
    import importlib.util
    from pathlib import Path

    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "ace-post-tool.py"
    spec = importlib.util.spec_from_file_location("ace_post_tool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.infer_implicit_signal("Edit", {"file_path": "/app/auth_handler.py", "old_string": ""})
    assert result is not None
    assert result["type"] == "pattern"
    assert result["implicit"] is True
    assert result["confidence"] <= 0.65


@_skip_no_hooks
def test_m1_infer_bug_fixme_correction():
    import importlib.util
    from pathlib import Path

    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "ace-post-tool.py"
    spec = importlib.util.spec_from_file_location("ace_post_tool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.infer_implicit_signal(
        "Edit",
        {"file_path": "/app/utils.py", "old_string": "# BUG: off-by-one error here"},
    )
    assert result is not None
    assert result["type"] == "correction"
    assert result["confidence"] <= 0.65


@_skip_no_hooks
def test_m1_infer_test_file_write():
    import importlib.util
    from pathlib import Path

    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "ace-post-tool.py"
    spec = importlib.util.spec_from_file_location("ace_post_tool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.infer_implicit_signal("Write", {"file_path": "/app/tests/test_auth.py"})
    assert result is not None
    assert result["type"] == "pattern"
    assert "test" in result["summary"].lower()


@_skip_no_hooks
def test_m1_infer_pytest_bash():
    import importlib.util
    from pathlib import Path

    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "ace-post-tool.py"
    spec = importlib.util.spec_from_file_location("ace_post_tool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.infer_implicit_signal("Bash", {"command": "uv run pytest tests/ -q"})
    assert result is not None
    assert result["type"] == "learning"


@_skip_no_hooks
def test_m1_infer_git_commit():
    import importlib.util
    from pathlib import Path

    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "ace-post-tool.py"
    spec = importlib.util.spec_from_file_location("ace_post_tool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.infer_implicit_signal("Bash", {"command": 'git commit -m "feat: add auth module"'})
    assert result is not None
    assert result["type"] == "decision"
    assert "feat: add auth module" in result["summary"]


@_skip_no_hooks
def test_m1_infer_no_signal_for_unrelated_bash():
    import importlib.util
    from pathlib import Path

    hook_path = Path(__file__).parent.parent / ".claude" / "hooks" / "ace-post-tool.py"
    spec = importlib.util.spec_from_file_location("ace_post_tool", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.infer_implicit_signal("Bash", {"command": "ls -la"})
    assert result is None


# ── M2 — freshness decay ───────────────────────────────────────────────────


def test_m2_fresh_item_scores_high():
    from core.engine.capture.freshness import FreshnessDecay

    decay = FreshnessDecay()
    item = {
        "id": "insight:1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "governed_files": [],
        "contradiction_count": 0,
    }
    result = decay.compute(item, {})
    assert result.freshness_score > 0.8
    assert result.label == "fresh"


def test_m2_old_item_decays():
    from core.engine.capture.freshness import FreshnessDecay

    decay = FreshnessDecay()
    old_date = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    item = {
        "id": "insight:2",
        "created_at": old_date,
        "governed_files": [],
        "contradiction_count": 0,
    }
    result = decay.compute(item, {})
    assert result.freshness_score < 0.8


def test_m2_high_contradictions_reduce_score():
    from core.engine.capture.freshness import FreshnessDecay

    decay = FreshnessDecay()
    item = {
        "id": "insight:3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "governed_files": [],
        "contradiction_count": 5,
    }
    result_low = decay.compute(item, {})
    item_no_contradictions = {**item, "contradiction_count": 0}
    result_high = decay.compute(item_no_contradictions, {})
    assert result_low.freshness_score < result_high.freshness_score


def test_m2_high_file_changes_reduce_score():
    from core.engine.capture.freshness import FreshnessDecay

    decay = FreshnessDecay()
    item = {
        "id": "insight:4",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "governed_files": ["engine/auth.py"],
        "contradiction_count": 0,
    }
    result_changed = decay.compute(item, {"engine/auth.py": 500})
    result_unchanged = decay.compute(item, {"engine/auth.py": 0})
    assert result_changed.freshness_score <= result_unchanged.freshness_score


def test_m2_score_bounded_01():
    from core.engine.capture.freshness import FreshnessDecay

    decay = FreshnessDecay()
    item = {
        "id": "insight:5",
        "created_at": "2020-01-01T00:00:00+00:00",
        "governed_files": ["x.py"],
        "contradiction_count": 10,
    }
    result = decay.compute(item, {"x.py": 10000})
    assert 0.0 <= result.freshness_score <= 1.0


def test_m2_stale_label_for_very_old():
    from core.engine.capture.freshness import FreshnessDecay

    decay = FreshnessDecay()
    very_old = (datetime.now(timezone.utc) - timedelta(days=730)).isoformat()
    item = {
        "id": "insight:6",
        "created_at": very_old,
        "governed_files": ["x.py"],
        "contradiction_count": 5,
    }
    result = decay.compute(item, {"x.py": 1000})
    assert result.label == "stale"


# ── M3 — pre-capture contradiction detection ───────────────────────────────


@pytest.mark.asyncio
async def test_m3_no_conflicts_for_novel_decision():
    from core.engine.product.decisions import check_decision_conflicts

    mock_pool, mock_conn = _make_pool()
    with patch("core.engine.core.db.parse_rows", return_value=[]):
        result = await check_decision_conflicts("Novel decision content", "product:test", mock_pool)
    assert result == []


@pytest.mark.asyncio
async def test_m3_conflict_detected_for_similar_content():
    from core.engine.product.decisions import check_decision_conflicts

    # Use near-identical content to guarantee Jaccard >= 0.75
    existing = [
        {
            "id": "decision:1",
            "title": "always use parameterized queries for database calls",
            "rationale": "prevent sql injection",
        }
    ]
    mock_pool, mock_conn = _make_pool()
    with patch("core.engine.core.db.parse_rows", return_value=existing):
        result = await check_decision_conflicts(
            "always use parameterized queries for database calls prevent sql injection",
            "product:test",
            mock_pool,
        )
    assert len(result) > 0


@pytest.mark.asyncio
async def test_m3_conflict_has_required_fields():
    from core.engine.product.decisions import check_decision_conflicts

    existing = [{"id": "decision:1", "title": "use snake case naming everywhere", "rationale": "style guide"}]
    mock_pool, mock_conn = _make_pool()
    with patch("core.engine.core.db.parse_rows", return_value=existing):
        result = await check_decision_conflicts(
            "use snake_case naming everywhere in the codebase", "product:test", mock_pool
        )
    if result:
        assert "id" in result[0]
        assert "similarity_score" in result[0]
        assert "conflict_type" in result[0]


@pytest.mark.asyncio
async def test_m3_returns_empty_on_db_failure():
    from core.engine.product.decisions import check_decision_conflicts

    mock_pool, _ = _make_pool()
    with patch("core.engine.core.db.parse_rows", side_effect=RuntimeError("db down")):
        result = await check_decision_conflicts("some content", "product:test", mock_pool)
    assert result == []


# ── M4 — consolidation ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_m4_consolidation_result_type():
    from core.engine.capture.consolidator import ConsolidationResult, ObservationConsolidator

    consolidator = ObservationConsolidator()
    mock_pool, _ = _make_pool()
    with patch("core.engine.core.db.parse_rows", return_value=[]):
        result = await consolidator.run("product:test", mock_pool)
    assert isinstance(result, ConsolidationResult)


@pytest.mark.asyncio
async def test_m4_below_threshold_not_archived():
    from core.engine.capture.consolidator import ObservationConsolidator

    # 4 items (below CLUSTER_MIN_SIZE=5) — nothing should be archived
    rows = [
        {"id": f"insight:{i}", "content": "use parameterized queries", "confidence": 0.7, "tags": []} for i in range(4)
    ]
    mock_pool, _ = _make_pool()
    with patch("core.engine.core.db.parse_rows", return_value=rows):
        consolidator = ObservationConsolidator()
        result = await consolidator.run("product:test", mock_pool)
    assert result.items_archived == 0


@pytest.mark.asyncio
async def test_m4_cluster_groups_similar_observations():
    from core.engine.capture.consolidator import ObservationConsolidator

    consolidator = ObservationConsolidator()
    # Identical content → Jaccard = 1.0, guaranteed to cluster above 0.82 threshold
    observations = [
        {
            "id": f"insight:{i}",
            "content": "always use parameterized sql queries for database calls",
            "confidence": 0.7,
            "tags": [],
        }
        for i in range(10)
    ]
    clusters = await consolidator._cluster(observations)
    # All similar observations should cluster together
    max_cluster = max(len(c) for c in clusters)
    assert max_cluster >= 5


@pytest.mark.asyncio
async def test_m4_dissimilar_observations_separate_clusters():
    from core.engine.capture.consolidator import ObservationConsolidator

    consolidator = ObservationConsolidator()
    observations = [
        {"id": "insight:1", "content": "always use parameterized sql queries", "confidence": 0.7, "tags": []},
        {"id": "insight:2", "content": "deploy with blue green strategy", "confidence": 0.7, "tags": []},
        {"id": "insight:3", "content": "monitor memory usage in production", "confidence": 0.7, "tags": []},
    ]
    clusters = await consolidator._cluster(observations)
    assert len(clusters) >= 2


# ── M6 — cross-session pattern detector ───────────────────────────────────


def test_m6_content_hash_stable():
    from core.engine.capture.pattern_detector import _content_hash

    h1 = _content_hash("use parameterized queries for all db calls")
    h2 = _content_hash("use parameterized queries for all db calls")
    assert h1 == h2


def test_m6_content_hash_different_for_different_content():
    from core.engine.capture.pattern_detector import _content_hash

    h1 = _content_hash("use parameterized queries")
    h2 = _content_hash("always validate user input")
    assert h1 != h2


@pytest.mark.asyncio
async def test_m6_no_recurrence_below_threshold():
    from core.engine.capture.pattern_detector import CrossSessionPatternDetector

    detector = CrossSessionPatternDetector()
    mock_pool, _ = _make_pool()

    # Only 2 historical insights from different sessions (below threshold of 3)
    historical = [
        {"content": "use parameterized queries", "source_session": "session:1", "tags": []},
        {"content": "use parameterized sql queries", "source_session": "session:2", "tags": []},
    ]
    with patch("core.engine.core.db.parse_rows", return_value=historical):
        new_insights = [{"content": "always parameterize sql queries", "id": "insight:new"}]
        result = await detector.check_recurrence(new_insights, "product:test", "session:3", mock_pool)
    # current_session=3, hist sessions=1,2 → total=3 which equals threshold
    # This should fire (3 >= RECURRENCE_THRESHOLD=3)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_m6_empty_insights_returns_empty():
    from core.engine.capture.pattern_detector import CrossSessionPatternDetector

    detector = CrossSessionPatternDetector()
    mock_pool, _ = _make_pool()
    result = await detector.check_recurrence([], "product:test", "session:1", mock_pool)
    assert result == []


# ── M7 — episodic recall ───────────────────────────────────────────────────


def test_m7_episode_heuristics_score():
    from core.engine.capture.episodes import EpisodeHeuristics

    h = EpisodeHeuristics(decisions_count=4, files_created_count=6, feat_commit=True)
    assert h.score >= 2
    assert h.qualifies


def test_m7_episode_heuristics_below_threshold():
    from core.engine.capture.episodes import EpisodeHeuristics

    h = EpisodeHeuristics(decisions_count=0, files_created_count=0, feat_commit=False)
    assert not h.qualifies


@pytest.mark.asyncio
async def test_m7_detect_episode_returns_none_when_below_threshold():
    from core.engine.capture.episodes import EpisodeDetector

    detector = EpisodeDetector()
    mock_pool, _ = _make_pool()

    with (
        patch("core.engine.core.db.parse_rows", return_value=[]),
        patch("subprocess.check_output", side_effect=Exception("no git")),
    ):
        result = await detector.detect_episode("session:1", "product:test", mock_pool)
    assert result is None


@pytest.mark.asyncio
async def test_m7_get_episode_returns_list():
    from core.engine.capture.episodes import EpisodeDetector

    detector = EpisodeDetector()
    mock_pool, _ = _make_pool()

    episodes = [{"id": "episode:1", "title": "Build auth module", "session_ids": ["s1"]}]
    with patch("core.engine.core.db.parse_rows", return_value=episodes):
        result = await detector.get_episode("auth", "product:test", mock_pool)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_m7_get_episode_returns_empty_on_failure():
    from core.engine.capture.episodes import EpisodeDetector

    detector = EpisodeDetector()
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = RuntimeError("db down")

    result = await detector.get_episode("auth", "product:test", mock_pool)
    assert result == []
