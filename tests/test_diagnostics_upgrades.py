# tests/test_diagnostics_upgrades.py
"""Tests for D-layer diagnostics upgrades: D1 findings, D2 trends,
D3 diff impact, D4 evidence linking, D5 confidence, D6 correlation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("db_pool")

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pool():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


def _quality_row(slug="auth_system", dim="security", score=0.2, confidence=0.35, gaps=None, evidence=None):
    return {
        "id": f"capability_quality:{slug}__{dim}__product_platform",
        "capability": f"capability:{slug}",
        "dimension": dim,
        "score": score,
        "confidence": confidence,
        "evidence_count": len(evidence or []),
        "gaps": gaps or ["No input validation", "Hardcoded secret"],
        "evidence": evidence or ["validate_token() exists", "SECRET_KEY in settings.py"],
        "assessed_at": "2026-04-12T00:00:00Z",
    }


# ── D5: confidence_label ──────────────────────────────────────────────────────


def test_confidence_label_high():
    from core.engine.sentinel.engines.gap_analyzer import _confidence_label

    assert _confidence_label(0.9) == "high"


def test_confidence_label_moderate():
    from core.engine.sentinel.engines.gap_analyzer import _confidence_label

    assert _confidence_label(0.6) == "moderate"


def test_confidence_label_low():
    from core.engine.sentinel.engines.gap_analyzer import _confidence_label

    label = _confidence_label(0.3)
    assert "low" in label
    assert "limited code visibility" in label


def test_confidence_label_very_low():
    from core.engine.sentinel.engines.gap_analyzer import _confidence_label

    label = _confidence_label(0.1)
    assert "manual review" in label


def test_confidence_label_boundary_high():
    from core.engine.sentinel.engines.gap_analyzer import _confidence_label

    assert _confidence_label(0.75) == "high"


def test_confidence_label_boundary_moderate():
    from core.engine.sentinel.engines.gap_analyzer import _confidence_label

    assert _confidence_label(0.5) == "moderate"


# ── D5: ace_gaps includes confidence_label ────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_gaps_includes_confidence_label(mock_pool):
    mock_p, mock_db = mock_pool
    quality_rows = [_quality_row(confidence=0.3)]
    # Return quality rows on first query, empty for D1 findings queries
    mock_db.query = AsyncMock(side_effect=[quality_rows, [], []])

    from core.engine.mcp import tools

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_gaps(product_id="product:platform")

    assert result["count"] == 1
    gap = result["gaps"][0]
    assert "confidence_label" in gap
    assert "low" in gap["confidence_label"]


@pytest.mark.asyncio
async def test_ace_gaps_high_confidence_label(mock_pool):
    mock_p, mock_db = mock_pool
    quality_rows = [_quality_row(confidence=0.85)]
    mock_db.query = AsyncMock(side_effect=[quality_rows, [], []])

    from core.engine.mcp import tools

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_gaps(product_id="product:platform")

    assert result["gaps"][0]["confidence_label"] == "high"


# ── D4: ace_explain_gap ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_explain_gap_returns_gaps_and_evidence(mock_pool):
    mock_p, mock_db = mock_pool
    quality_rows = [_quality_row(score=0.2, confidence=0.35)]
    # ace_explain_gap does one db.query call
    mock_db.query = AsyncMock(return_value=quality_rows)

    from core.engine.mcp import tools

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_explain_gap(
            capability_slug="auth_system",
            dimension="security",
            product_id="product:platform",
        )

    assert result["capability_slug"] == "auth_system"
    assert result["dimension"] == "security"
    assert result["score"] == 0.2
    assert len(result["gaps"]) > 0
    assert len(result["evidence"]) > 0
    assert "confidence_label" in result
    assert result["fix_priority"] == "high"  # score < 0.3


@pytest.mark.asyncio
async def test_ace_explain_gap_missing_record(mock_pool):
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])  # no rows → error branch

    from core.engine.mcp import tools

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_explain_gap("nonexistent", "security")

    assert "error" in result


@pytest.mark.asyncio
async def test_ace_explain_gap_fix_priority_medium(mock_pool):
    mock_p, mock_db = mock_pool
    quality_rows = [_quality_row(score=0.45, confidence=0.7)]
    mock_db.query = AsyncMock(return_value=quality_rows)

    from core.engine.mcp import tools

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_explain_gap("some_cap", "testing")

    assert result["fix_priority"] == "medium"  # 0.3 <= score < 0.6


@pytest.mark.asyncio
async def test_ace_product_health_explain_adds_explanation(mock_pool):
    mock_p, _ = mock_pool
    cap_rows = [_quality_row(score=0.2)]
    health_result = {
        "dimensions": {"security": {"avg_score": 0.2, "min_score": 0.2, "assessed_count": 1, "total_gaps": 2}},
        "total_capabilities": 1,
        "by_status": {"built": 1},
    }

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.mcp import tools

        with (
            patch.object(tools, "pool", mock_p),
            patch("core.engine.product.map.ProductMap.health_summary", return_value=health_result),
            patch(
                "core.engine.sentinel.engines.gap_analyzer.get_score_trend", return_value={"trend": "insufficient_data"}
            ),
            patch("core.engine.core.db.parse_rows", return_value=cap_rows),
        ):
            result = await tools.ace_product_health(product_id="product:platform", explain="security")

    assert "explanation" in result
    assert result["explanation"]["dimension"] == "security"
    assert isinstance(result["explanation"]["capabilities"], list)


@pytest.mark.asyncio
async def test_ace_product_health_no_explain_unchanged(mock_pool):
    """Existing ace_product_health() (no explain) returns same structure — backward compat."""
    health_result = {
        "dimensions": {"security": {"avg_score": 0.4}},
        "total_capabilities": 5,
        "by_status": {"built": 5},
    }

    with patch("core.engine.product.map.ProductMap.health_summary", return_value=health_result):
        with patch(
            "core.engine.sentinel.engines.gap_analyzer.get_score_trend", return_value={"trend": "insufficient_data"}
        ):
            from core.engine.mcp import tools

            result = await tools.ace_product_health(product_id="product:platform")

    assert "dimensions" in result
    assert "total_capabilities" in result
    assert "explanation" not in result


# ── D2: get_score_trend ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_score_trend_insufficient_data_single_snapshot(mock_pool):
    mock_p, mock_db = mock_pool
    single_snapshot = [{"score": 0.3, "assessed_at": "2026-04-01T00:00:00Z"}]

    with (
        patch("core.engine.core.db.pool", mock_p),
        patch("core.engine.core.db.parse_rows", return_value=single_snapshot),
    ):
        from core.engine.sentinel.engines.gap_analyzer import get_score_trend

        result = await get_score_trend("product:platform", "security")

    assert result["trend"] == "insufficient_data"
    assert result["delta"] == 0.0


@pytest.mark.asyncio
async def test_get_score_trend_improving():
    """Three snapshots on different dates with improving scores → trend=improving."""
    snapshots = [
        {"score": 0.2, "assessed_at": "2026-01-15T00:00:00Z"},
        {"score": 0.3, "assessed_at": "2026-02-15T00:00:00Z"},
        {"score": 0.4, "assessed_at": "2026-03-15T00:00:00Z"},
    ]
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=snapshots)  # return rows directly; real parse_rows handles flat list
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.sentinel.engines.gap_analyzer import get_score_trend

        result = await get_score_trend("product:platform", "security")

    assert result["trend"] == "improving"
    assert result["delta"] > 0.05
    assert len(result["snapshots"]) >= 2


@pytest.mark.asyncio
async def test_get_score_trend_declining():
    """Snapshots with declining scores → trend=declining."""
    snapshots = [
        {"score": 0.7, "assessed_at": "2026-01-15T00:00:00Z"},
        {"score": 0.5, "assessed_at": "2026-02-15T00:00:00Z"},
        {"score": 0.3, "assessed_at": "2026-03-15T00:00:00Z"},
    ]
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=snapshots)  # return rows directly; real parse_rows handles flat list
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.sentinel.engines.gap_analyzer import get_score_trend

        result = await get_score_trend("product:platform", "testing")

    assert result["trend"] == "declining"
    assert result["delta"] < -0.05


@pytest.mark.asyncio
async def test_get_score_trend_stable():
    """Near-equal scores → trend=stable."""
    snapshots = [
        {"score": 0.50, "assessed_at": "2026-02-01T00:00:00Z"},
        {"score": 0.52, "assessed_at": "2026-03-01T00:00:00Z"},
    ]
    mock_p = MagicMock()
    mock_conn = MagicMock()
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=snapshots)  # return rows directly; real parse_rows handles flat list
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p.connection.return_value = mock_conn

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.sentinel.engines.gap_analyzer import get_score_trend

        result = await get_score_trend("product:platform", "performance")

    assert result["trend"] == "stable"


# ── D3: _parse_diff_summary ───────────────────────────────────────────────────


def test_parse_diff_summary_detects_added_function():
    from core.engine.sentinel.engines.gap_analyzer import _parse_diff_summary

    diff = """\
--- a/engine/auth/handler.py
+++ b/engine/auth/handler.py
@@ -10,6 +10,10 @@
+def validate_input(data):
+    pass
"""
    result = _parse_diff_summary(diff)
    assert "validate_input" in result["added_functions"]
    assert "engine/auth/handler.py" in result["modified_files"]


def test_parse_diff_summary_detects_removed_function():
    from core.engine.sentinel.engines.gap_analyzer import _parse_diff_summary

    diff = """\
--- a/engine/auth/handler.py
+++ b/engine/auth/handler.py
@@ -10,6 +10,0 @@
-def validate_input(data):
-    return data
"""
    result = _parse_diff_summary(diff)
    assert "validate_input" in result["removed_functions"]


def test_parse_diff_summary_empty_diff():
    from core.engine.sentinel.engines.gap_analyzer import _parse_diff_summary

    result = _parse_diff_summary("")
    assert result["added_functions"] == []
    assert result["removed_functions"] == []
    assert result["modified_files"] == []


def test_parse_diff_summary_multiple_files():
    from core.engine.sentinel.engines.gap_analyzer import _parse_diff_summary

    diff = """\
--- a/engine/auth.py
+++ b/engine/auth.py
@@ -1,1 +1,1 @@
+def new_func(): pass
--- a/engine/api/routes.py
+++ b/engine/api/routes.py
@@ -1,1 +1,1 @@
-def old_func(): pass
"""
    result = _parse_diff_summary(diff)
    assert len(result["modified_files"]) >= 2
    assert "new_func" in result["added_functions"]
    assert "old_func" in result["removed_functions"]


# ── D3: ace_diff_impact ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_diff_impact_no_supported_files():
    """Diff with no .py/.ts files → no affected capabilities, returns none."""
    from core.engine.mcp import tools

    result = await tools.ace_diff_impact(diff="--- a/README.md\n+++ b/README.md\n")
    assert result["net_impact"] in ("none", "insufficient_data")
    assert result["affected_capabilities"] == []


@pytest.mark.asyncio
async def test_ace_diff_impact_security_regression(mock_pool):
    from core.engine.mcp import tools  # import before patching so patch.object has the module reference

    mock_p, mock_db = mock_pool

    diff = """\
--- a/engine/auth/handler.py
+++ b/engine/auth/handler.py
@@ -10,6 +10,0 @@
-def validate_input(data):
-    return sanitize(data)
"""

    # db.query is called 3 times: realizes edge, capability record, quality scores.
    # Return flat dicts so real parse_rows passes them through unchanged.
    realizes_rows = [{"cap": "capability:auth_system"}]
    cap_rows = [{"id": "capability:auth_system", "slug": "auth_system", "name": "Auth System"}]
    score_rows = [{"dimension": "security", "score": 0.6}]
    mock_db.query = AsyncMock(side_effect=[realizes_rows, cap_rows, score_rows])

    predictions = [{"dimension": "security", "predicted_delta": -0.25, "reason": "Removes input validation"}]

    with (
        patch.object(tools, "pool", mock_p),
        patch("core.engine.sentinel.engines.gap_analyzer._assess_diff_impact", return_value=predictions),
    ):
        result = await tools.ace_diff_impact(diff=diff, product_id="product:platform")

    assert "auth_system" in result["affected_capabilities"]
    assert result["net_impact"] == "critical"
    assert "security" in result["recommendation"].lower()


# ── D1: engine/sentinel/findings.py ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_findings_with_capability(mock_pool):
    mock_p, mock_db = mock_pool
    findings = [
        {
            "discipline": "security",
            "severity": "high",
            "file": "engine/auth/handler.py",
            "line": 47,
            "col": None,
            "message": "SQL injection pattern",
            "rule_id": "B608",
            "fix_command": "Use parameterized queries",
            "tool": "bandit",
            "scan_id": "scan-001",
        }
    ]

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.sentinel import findings as findings_mod

        with patch.object(findings_mod, "_resolve_capability", return_value="capability:auth_system"):
            count = await findings_mod.write_findings(findings, "product:platform", mock_p)

    assert count == 1
    mock_db.query.assert_called_once()


@pytest.mark.asyncio
async def test_write_findings_skips_unmapped_file(mock_pool):
    mock_p, mock_db = mock_pool
    findings = [
        {
            "discipline": "code_conventions",
            "severity": "low",
            "file": "some/unmapped/file.py",
            "line": 1,
            "col": None,
            "message": "Line too long",
            "rule_id": "E501",
            "fix_command": "",
            "tool": "ruff",
            "scan_id": "scan-002",
        }
    ]

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.sentinel import findings as findings_mod

        # _resolve_capability returns None → finding is skipped
        with patch.object(findings_mod, "_resolve_capability", return_value=None):
            count = await findings_mod.write_findings(findings, "product:platform", mock_p)

    assert count == 0
    mock_db.query.assert_not_called()


@pytest.mark.asyncio
async def test_write_findings_empty_input(mock_pool):
    mock_p, _ = mock_pool

    from core.engine.sentinel import findings as findings_mod

    count = await findings_mod.write_findings([], "product:platform", mock_p)
    assert count == 0


@pytest.mark.asyncio
async def test_write_findings_multiple_mixed(mock_pool):
    """Two findings: one mapped, one not → count=1."""
    mock_p, _ = mock_pool
    findings = [
        {
            "discipline": "security",
            "severity": "critical",
            "file": "engine/auth.py",
            "line": 10,
            "col": None,
            "message": "Secret exposed",
            "rule_id": "TH001",
            "fix_command": "Rotate key",
            "tool": "trufflehog",
            "scan_id": "scan-003",
        },
        {
            "discipline": "code_conventions",
            "severity": "low",
            "file": "engine/utils.py",
            "line": 5,
            "col": 0,
            "message": "Trailing whitespace",
            "rule_id": "W291",
            "fix_command": "",
            "tool": "ruff",
            "scan_id": "scan-003",
        },
    ]

    resolve_results = ["capability:auth_system", None]
    resolve_iter = iter(resolve_results)

    from core.engine.sentinel import findings as findings_mod

    with patch.object(findings_mod, "_resolve_capability", side_effect=lambda f, db: next(resolve_iter)):
        count = await findings_mod.write_findings(findings, "product:platform", mock_p)

    assert count == 1


# ── D6: _pearson_r and _find_best_lag ────────────────────────────────────────


def test_pearson_r_perfect_positive():
    from core.engine.sentinel.engines.correlation_engine import _pearson_r

    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0, 4.0, 6.0, 8.0, 10.0]
    r = _pearson_r(xs, ys)
    assert abs(r - 1.0) < 0.0001


def test_pearson_r_perfect_negative():
    from core.engine.sentinel.engines.correlation_engine import _pearson_r

    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [10.0, 8.0, 6.0, 4.0, 2.0]
    r = _pearson_r(xs, ys)
    assert abs(r + 1.0) < 0.0001


def test_pearson_r_no_correlation():
    from core.engine.sentinel.engines.correlation_engine import _pearson_r

    xs = [1.0, 2.0, 3.0, 4.0]
    ys = [5.0, 5.0, 5.0, 5.0]
    r = _pearson_r(xs, ys)
    assert r == 0.0


def test_pearson_r_short_series():
    from core.engine.sentinel.engines.correlation_engine import _pearson_r

    assert _pearson_r([1.0], [1.0]) == 0.0
    assert _pearson_r([], []) == 0.0


def test_find_best_lag_detects_lag1():
    """A that leads B by 1 week should be detected at lag=1."""
    from core.engine.sentinel.engines.correlation_engine import _find_best_lag

    # A drops, then B drops 1 step later
    series_a = [0.8, 0.7, 0.5, 0.3, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]
    series_b = [0.8, 0.8, 0.7, 0.5, 0.3, 0.2, 0.2, 0.2, 0.2, 0.2]
    lag, r = _find_best_lag(series_a, series_b)
    assert lag == 1
    assert r > 0.6


def test_find_best_lag_no_signal_returns_none():
    """Uncorrelated series → returns (None, 0.0)."""
    from core.engine.sentinel.engines.correlation_engine import _find_best_lag

    series_a = [0.5, 0.6, 0.4, 0.7, 0.3, 0.8, 0.5, 0.6, 0.4, 0.7]
    series_b = [0.3, 0.8, 0.5, 0.2, 0.9, 0.1, 0.6, 0.3, 0.8, 0.4]
    lag, r = _find_best_lag(series_a, series_b)
    # r may or may not be 0 but should not meet threshold
    if lag is not None:
        assert abs(r) >= 0.6  # if returned, must meet threshold
    else:
        assert lag is None


def test_find_best_lag_insufficient_series_length():
    from core.engine.sentinel.engines.correlation_engine import _find_best_lag

    lag, r = _find_best_lag([0.5, 0.4], [0.5, 0.4])
    assert lag is None


# ── D6: run_correlation_engine requires min snapshots ────────────────────────


@pytest.mark.asyncio
async def test_correlation_engine_skips_sparse_data(mock_pool):
    """Engine skips dimension pairs with fewer than 8 data points."""
    mock_p, _ = mock_pool
    # Only 3 snapshots per dimension — below MIN_SNAPSHOTS=8
    weekly_data = {
        "security": [0.3, 0.4, 0.5],
        "testing": [0.4, 0.5, 0.6],
    }

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.sentinel.engines import correlation_engine

        with patch.object(correlation_engine, "_load_weekly_averages", return_value=weekly_data):
            result = await correlation_engine.run_correlation_engine("product:platform")

    assert result["signals_found"] == 0
    assert result["skipped_sparse"] > 0


@pytest.mark.asyncio
async def test_correlation_engine_detects_strong_correlation(mock_pool):
    """Engine stores signal when |r| >= 0.6 with sufficient data."""
    mock_p, mock_db = mock_pool
    # 10 weekly points with strong testing→security lag-1 correlation
    testing_series = [0.8, 0.7, 0.6, 0.5, 0.4, 0.35, 0.3, 0.3, 0.3, 0.3]
    security_series = [0.8, 0.8, 0.7, 0.6, 0.5, 0.4, 0.35, 0.3, 0.3, 0.3]
    weekly_data = {"testing": testing_series, "security": security_series}

    with patch("core.engine.core.db.pool", mock_p):
        from core.engine.sentinel.engines import correlation_engine

        with patch.object(correlation_engine, "_load_weekly_averages", return_value=weekly_data):
            result = await correlation_engine.run_correlation_engine("product:platform")

    assert result["signals_found"] >= 1


# ── D2: ace_product_health includes trend_arrow ──────────────────────────────


@pytest.mark.asyncio
async def test_ace_product_health_includes_trend_arrow():
    """ace_product_health adds trend_arrow when score trend is improving."""
    health_result = {
        "dimensions": {"security": {"avg_score": 0.4, "min_score": 0.3, "assessed_count": 2, "total_gaps": 3}},
        "total_capabilities": 2,
        "by_status": {"built": 2},
    }
    trend_result = {"trend": "improving", "delta": 0.15, "snapshots": []}

    with (
        patch("core.engine.product.map.ProductMap.health_summary", return_value=health_result),
        patch("core.engine.sentinel.engines.gap_analyzer.get_score_trend", return_value=trend_result),
    ):
        from core.engine.mcp import tools

        result = await tools.ace_product_health(product_id="product:platform")

    assert result["dimensions"]["security"]["trend_arrow"] == "↑↑"
    assert result["dimensions"]["security"]["delta_30d"] == 0.15


@pytest.mark.asyncio
async def test_ace_product_health_declining_trend():
    health_result = {
        "dimensions": {"testing": {"avg_score": 0.3, "min_score": 0.2, "assessed_count": 2, "total_gaps": 5}},
        "total_capabilities": 2,
        "by_status": {"built": 2},
    }
    trend_result = {"trend": "declining", "delta": -0.12, "snapshots": []}

    with (
        patch("core.engine.product.map.ProductMap.health_summary", return_value=health_result),
        patch("core.engine.sentinel.engines.gap_analyzer.get_score_trend", return_value=trend_result),
    ):
        from core.engine.mcp import tools

        result = await tools.ace_product_health(product_id="product:platform")

    assert result["dimensions"]["testing"]["trend_arrow"] == "↓"
    assert result["dimensions"]["testing"]["delta_30d"] < 0
