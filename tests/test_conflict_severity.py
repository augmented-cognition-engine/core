# tests/test_conflict_severity.py
"""Tests for line-level conflict severity analysis."""

from core.engine.pm.git import (
    compute_conflict_severity,
    max_severity,
    parse_changed_lines,
    predict_merge_conflicts,
)


def test_parse_single_hunk():
    """Parse a single-hunk diff into file->line mapping."""
    diff = (
        "diff --git a/engine/api/main.py b/engine/api/main.py\n"
        "--- a/engine/api/main.py\n"
        "+++ b/engine/api/main.py\n"
        "@@ -10,3 +10,5 @@ some context\n"
        "+new line 1\n"
        "+new line 2\n"
    )
    result = parse_changed_lines(diff)
    assert "engine/api/main.py" in result
    assert result["engine/api/main.py"] == {10, 11, 12, 13, 14}


def test_parse_multiple_files():
    """Parse diff with changes in multiple files."""
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -5,0 +5,2 @@\n"
        "+added\n"
        "diff --git a/bar.py b/bar.py\n"
        "--- a/bar.py\n"
        "+++ b/bar.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    result = parse_changed_lines(diff)
    assert "foo.py" in result
    assert "bar.py" in result


def test_parse_empty_diff():
    """Empty diff returns empty dict."""
    assert parse_changed_lines("") == {}


def test_parse_single_line_hunk():
    """Hunk with no count (single line change)."""
    diff = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -3 +3 @@\n-old\n+new\n"
    result = parse_changed_lines(diff)
    assert result["x.py"] == {3}


# --- Task 2: compute_conflict_severity ---


def test_severity_high_same_lines():
    lines_a = {"foo.py": {10, 11, 12}}
    lines_b = {"foo.py": {11, 13}}
    severity, details = compute_conflict_severity(lines_a, lines_b)
    assert severity == "high"
    assert details[0]["file"] == "foo.py"
    assert 11 in details[0]["overlapping_lines"]


def test_severity_medium_same_file():
    lines_a = {"foo.py": {1, 2, 3}}
    lines_b = {"foo.py": {10, 11}}
    severity, details = compute_conflict_severity(lines_a, lines_b)
    assert severity == "medium"


def test_severity_low_same_dir():
    lines_a = {"engine/api/main.py": {1, 2}}
    lines_b = {"engine/api/routes.py": {5, 6}}
    severity, details = compute_conflict_severity(lines_a, lines_b)
    assert severity == "low"


def test_severity_none_no_overlap():
    lines_a = {"core/engine/pm/git.py": {1}}
    lines_b = {"portal/src/App.tsx": {1}}
    severity, _ = compute_conflict_severity(lines_a, lines_b)
    assert severity == "none"


def test_severity_empty_inputs():
    severity, _ = compute_conflict_severity({}, {})
    assert severity == "none"


# --- Task 3: predict_merge_conflicts severity + max_severity ---


def test_predict_merge_conflicts_returns_severity():
    wis = [
        {"id": "wi:1", "files_touched": ["core/engine/api/main.py"]},
        {"id": "wi:2", "files_touched": ["core/engine/api/main.py"]},
    ]
    conflicts = predict_merge_conflicts(wis)
    assert len(conflicts) == 1
    assert conflicts[0]["severity"] == "high"


def test_predict_dir_overlap_severity():
    wis = [
        {"id": "wi:1", "files_touched": ["engine/api/main.py"]},
        {"id": "wi:2", "files_touched": ["engine/api/routes.py"]},
    ]
    conflicts = predict_merge_conflicts(wis)
    assert len(conflicts) == 1
    assert conflicts[0]["severity"] == "low"


def test_max_severity_empty():
    assert max_severity([]) == "none"


def test_max_severity_picks_highest():
    assert max_severity([{"severity": "low"}, {"severity": "high"}]) == "high"
    assert max_severity([{"severity": "medium"}]) == "medium"


# --- Task 7: check_live_conflicts ---

from unittest.mock import MagicMock, patch

from core.engine.pm.git import check_live_conflicts


def test_check_live_conflicts_no_branches():
    """Returns empty list when fewer than 2 WI branches exist."""
    with patch("core.engine.pm.git.Repo") as MockRepo:
        mock_repo = MockRepo.return_value
        mock_repo.branches = []

        result = check_live_conflicts("init_abc", 1, [{"id": "wi:1"}], "/tmp/repo")
        assert result == []


def test_check_live_conflicts_detects_overlap():
    """Detects file overlap between two WI branches."""
    diff_output = "diff --git a/api.py b/api.py\n--- a/api.py\n+++ b/api.py\n@@ -10,3 +10,5 @@\n+new\n"

    with patch("core.engine.pm.git.Repo") as MockRepo:
        mock_repo = MockRepo.return_value
        branch_a = MagicMock()
        branch_a.name = "ace/abc/1/wi-0-task-a"
        branch_b = MagicMock()
        branch_b.name = "ace/abc/1/wi-1-task-b"
        mock_repo.branches = [branch_a, branch_b]
        mock_repo.active_branch.name = "master"
        mock_repo.git.diff.return_value = diff_output

        wis = [
            {"id": "wi:1", "title": "Task A"},
            {"id": "wi:2", "title": "Task B"},
        ]
        result = check_live_conflicts("abc", 1, wis, "/tmp/repo")

        # Both branches change same file same lines -> should detect conflict
        assert len(result) >= 1
        assert result[0]["severity"] in ("high", "medium")


def test_check_live_conflicts_no_overlap():
    """No conflicts when branches touch different files."""
    diff_a = "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1,1 +1,2 @@\n+new\n"
    diff_b = "diff --git a/bar.py b/bar.py\n--- a/bar.py\n+++ b/bar.py\n@@ -5,1 +5,2 @@\n+other\n"

    with patch("core.engine.pm.git.Repo") as MockRepo:
        mock_repo = MockRepo.return_value
        branch_a = MagicMock()
        branch_a.name = "ace/abc/1/wi-0-task-a"
        branch_b = MagicMock()
        branch_b.name = "ace/abc/1/wi-1-task-b"
        mock_repo.branches = [branch_a, branch_b]
        mock_repo.active_branch.name = "master"
        # Return different diffs for different branch comparisons
        mock_repo.git.diff.side_effect = [diff_a, diff_b]

        wis = [
            {"id": "wi:1", "title": "Task A"},
            {"id": "wi:2", "title": "Task B"},
        ]
        result = check_live_conflicts("abc", 1, wis, "/tmp/repo")

        assert len(result) == 0
