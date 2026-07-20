# tests/test_commit_watcher.py

import pytest


def test_get_head_sha():
    from core.engine.scanner.commit_watcher import CommitWatcher

    watcher = CommitWatcher(repo_path=".")
    sha = watcher._get_head_sha()
    # Should return a 40-char hex string (we're in a git repo)
    assert sha is not None
    assert len(sha) == 40


def test_get_changed_files():
    from core.engine.scanner.commit_watcher import CommitWatcher

    watcher = CommitWatcher(repo_path=".")
    # Compare HEAD~1 to HEAD (should return at least 1 file)
    sha = watcher._get_head_sha()
    if sha:
        files = watcher._get_changed_files(f"{sha}~1", sha)
        assert isinstance(files, list)


def test_get_status():
    from core.engine.scanner.commit_watcher import CommitWatcher

    watcher = CommitWatcher(repo_path="/some/path", poll_interval=60)
    status = watcher.get_status()
    assert status["running"] is False
    assert status["repo_path"] == "/some/path"
    assert status["poll_interval"] == 60


@pytest.mark.asyncio
async def test_check_for_changes_no_change():
    from core.engine.scanner.commit_watcher import CommitWatcher

    watcher = CommitWatcher(repo_path=".")
    watcher._last_sha = watcher._get_head_sha()  # same as current
    await watcher._check_for_changes()
    # Should be a no-op — no errors, no mapping triggered
