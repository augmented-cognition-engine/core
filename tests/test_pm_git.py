# tests/test_pm_git.py
"""Tests for GitBranchManager and merge conflict prediction."""

import os
import tempfile

import pytest
from git import Repo


@pytest.fixture
def temp_repo():
    """Create a temporary git repo with an initial commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Do not inherit the developer's global init.defaultBranch. These
        # tests explicitly exercise a repository whose base is `master`.
        repo = Repo.init(tmpdir, initial_branch="master")
        # Configure git user for merge commits
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "test@test.com").release()
        # Create initial file and commit
        readme = os.path.join(tmpdir, "README.md")
        with open(readme, "w") as f:
            f.write("# Test Repo\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        yield repo


@pytest.fixture
def git_manager(temp_repo):
    from core.engine.pm.git import GitBranchManager

    return GitBranchManager(repo_path=temp_repo.working_dir)


# --- Branch lifecycle tests ---


def test_create_branch(git_manager, temp_repo):
    """Create a work item branch from base."""
    branch_name = "ace/init-123/1/wi-0-create-schema"
    git_manager.create_branch(branch_name, from_branch="master")
    assert branch_name in [b.name for b in temp_repo.branches]


def test_create_branch_default_base(git_manager, temp_repo):
    """Create branch defaults to current HEAD branch."""
    branch_name = "ace/init-123/1/wi-1-research"
    git_manager.create_branch(branch_name)
    assert branch_name in [b.name for b in temp_repo.branches]


def test_branch_naming_convention(git_manager):
    """Branch name follows ace/<init-id>/<ms-seq>/wi-<n>-<slug> pattern."""
    name = git_manager.make_branch_name("init:abc123", 1, 0, "Create Brand Schema")
    assert name == "ace/abc123/1/wi-0-create-brand-schema"


def test_merge_branch_clean(git_manager, temp_repo):
    """Clean merge — no conflicts."""
    # Create work on a branch
    git_manager.create_branch("ace/init-1/1/wi-0-feature", from_branch="master")
    temp_repo.heads["ace/init-1/1/wi-0-feature"].checkout()
    filepath = os.path.join(temp_repo.working_dir, "feature.py")
    with open(filepath, "w") as f:
        f.write("def feature(): pass\n")
    temp_repo.index.add(["feature.py"])
    temp_repo.index.commit("Add feature")

    # Merge back
    temp_repo.heads["master"].checkout()
    result = git_manager.merge_branch("ace/init-1/1/wi-0-feature", into="master")
    assert result["success"] is True
    assert result["conflicts"] == []


def test_merge_branch_conflict(git_manager, temp_repo):
    """Merge with conflicts detected."""
    readme_path = os.path.join(temp_repo.working_dir, "README.md")

    # Make a second commit on master first so branches diverge
    with open(readme_path, "w") as f:
        f.write("# Base version\nLine 2\n")
    temp_repo.index.add(["README.md"])
    temp_repo.index.commit("Base commit")

    git_manager.create_branch("ace/init-1/1/wi-0-a", from_branch="master")
    git_manager.create_branch("ace/init-1/1/wi-1-b", from_branch="master")

    # Branch A modifies README line 1
    temp_repo.heads["ace/init-1/1/wi-0-a"].checkout()
    with open(readme_path, "w") as f:
        f.write("# Branch A version\nLine 2\n")
    temp_repo.index.add(["README.md"])
    temp_repo.index.commit("Branch A change")

    # Branch B also modifies README line 1
    temp_repo.heads["ace/init-1/1/wi-1-b"].checkout()
    with open(readme_path, "w") as f:
        f.write("# Branch B version\nLine 2\n")
    temp_repo.index.add(["README.md"])
    temp_repo.index.commit("Branch B change")

    # Merge A into master (should be clean)
    temp_repo.heads["master"].checkout()
    result_a = git_manager.merge_branch("ace/init-1/1/wi-0-a", into="master")
    assert result_a["success"] is True

    # Merge B into master — should conflict (both changed same line)
    result_b = git_manager.merge_branch("ace/init-1/1/wi-1-b", into="master")
    assert result_b["success"] is False
    assert len(result_b["conflicts"]) > 0


def test_cleanup_branch(git_manager, temp_repo):
    """Delete a branch after merge."""
    git_manager.create_branch("ace/init-1/1/wi-0-temp", from_branch="master")
    assert "ace/init-1/1/wi-0-temp" in [b.name for b in temp_repo.branches]
    git_manager.delete_branch("ace/init-1/1/wi-0-temp")
    assert "ace/init-1/1/wi-0-temp" not in [b.name for b in temp_repo.branches]


def test_integration_branch(git_manager, temp_repo):
    """Create milestone integration branch and merge work items into it."""
    # Create two work item branches with non-conflicting changes
    git_manager.create_branch("ace/init-1/1/wi-0-schema", from_branch="master")
    temp_repo.heads["ace/init-1/1/wi-0-schema"].checkout()
    with open(os.path.join(temp_repo.working_dir, "schema.py"), "w") as f:
        f.write("# schema\n")
    temp_repo.index.add(["schema.py"])
    temp_repo.index.commit("Add schema")

    temp_repo.heads["master"].checkout()
    git_manager.create_branch("ace/init-1/1/wi-1-tests", from_branch="master")
    temp_repo.heads["ace/init-1/1/wi-1-tests"].checkout()
    with open(os.path.join(temp_repo.working_dir, "test_schema.py"), "w") as f:
        f.write("# tests\n")
    temp_repo.index.add(["test_schema.py"])
    temp_repo.index.commit("Add tests")

    # Create integration branch from master
    temp_repo.heads["master"].checkout()
    int_branch = git_manager.create_integration_branch("init-1", 1, from_branch="master")
    assert int_branch == "ace/init-1/m1-integration"

    result1 = git_manager.merge_branch("ace/init-1/1/wi-0-schema", into=int_branch)
    assert result1["success"] is True
    result2 = git_manager.merge_branch("ace/init-1/1/wi-1-tests", into=int_branch)
    assert result2["success"] is True


def test_diff_files(git_manager, temp_repo):
    """Get list of files changed between branches."""
    git_manager.create_branch("ace/init-1/1/wi-0-feature", from_branch="master")
    temp_repo.heads["ace/init-1/1/wi-0-feature"].checkout()
    with open(os.path.join(temp_repo.working_dir, "new_file.py"), "w") as f:
        f.write("new content\n")
    temp_repo.index.add(["new_file.py"])
    temp_repo.index.commit("Add new file")

    files = git_manager.diff_files("ace/init-1/1/wi-0-feature", "master")
    assert "new_file.py" in files


# --- Conflict prediction tests (pure functions, no git) ---


def test_predict_merge_conflicts_clean():
    """No file or directory overlap returns empty conflict list."""
    from core.engine.pm.git import predict_merge_conflicts

    items = [
        {"id": "wi:1", "files_touched": ["src/components/button.py"]},
        {"id": "wi:2", "files_touched": ["src/models/user.py"]},
    ]
    conflicts = predict_merge_conflicts(items)
    assert conflicts == []


def test_predict_merge_conflicts_file_overlap():
    """Direct file overlap returns run_sequentially recommendation."""
    from core.engine.pm.git import predict_merge_conflicts

    items = [
        {"id": "wi:1", "files_touched": ["src/main.py", "src/utils.py"]},
        {"id": "wi:2", "files_touched": ["src/main.py", "src/other.py"]},
    ]
    conflicts = predict_merge_conflicts(items)
    assert len(conflicts) == 1
    assert conflicts[0]["recommendation"] == "run_sequentially"
    assert "src/main.py" in conflicts[0]["conflicting_files"]


def test_predict_merge_conflicts_dir_overlap():
    """Directory-level overlap returns run_sequentially_or_review."""
    from core.engine.pm.git import predict_merge_conflicts

    items = [
        {"id": "wi:1", "files_touched": ["src/components/button.py"]},
        {"id": "wi:2", "files_touched": ["src/components/card.py"]},
    ]
    conflicts = predict_merge_conflicts(items)
    assert len(conflicts) == 1
    assert conflicts[0]["recommendation"] == "run_sequentially_or_review"
    assert "src/components" in conflicts[0]["conflicting_dirs"]


def test_predict_merge_conflicts_both():
    """File overlap takes priority — no duplicate dir-only entry."""
    from core.engine.pm.git import predict_merge_conflicts

    items = [
        {"id": "wi:1", "files_touched": ["src/api/routes.py"]},
        {"id": "wi:2", "files_touched": ["src/api/routes.py", "src/api/models.py"]},
    ]
    conflicts = predict_merge_conflicts(items)
    # Should have one conflict for file overlap, not a duplicate for dir
    file_conflicts = [c for c in conflicts if "conflicting_files" in c]
    dir_conflicts = [c for c in conflicts if "conflicting_dirs" in c]
    assert len(file_conflicts) == 1
    assert len(dir_conflicts) == 0  # already covered by file overlap


def test_predict_merge_conflicts_empty_files():
    """Items with no files_touched don't conflict."""
    from core.engine.pm.git import predict_merge_conflicts

    items = [
        {"id": "wi:1", "files_touched": None},
        {"id": "wi:2", "files_touched": []},
    ]
    conflicts = predict_merge_conflicts(items)
    assert conflicts == []


def test_predict_merge_conflicts_three_way():
    """Three items — pairwise conflict detection."""
    from core.engine.pm.git import predict_merge_conflicts

    items = [
        {"id": "wi:1", "files_touched": ["src/components/a.py"]},
        {"id": "wi:2", "files_touched": ["src/models/b.py"]},
        {"id": "wi:3", "files_touched": ["src/components/a.py"]},  # conflicts with wi:1
    ]
    conflicts = predict_merge_conflicts(items)
    # wi:1 and wi:3 have file overlap; wi:1 and wi:3 share dir (covered by file overlap)
    # wi:2 has no overlap with either
    file_conflicts = [c for c in conflicts if "conflicting_files" in c]
    assert len(file_conflicts) == 1
    assert set([file_conflicts[0]["item_a"], file_conflicts[0]["item_b"]]) == {"wi:1", "wi:3"}
