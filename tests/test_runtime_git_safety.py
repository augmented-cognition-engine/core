"""Tests for pre-edit git safety."""

from core.engine.runtime.tools.git_safety import pre_edit_save


def test_pre_edit_save_returns_none_outside_git(tmp_path):
    """Outside a git repo, should return None."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    result = pre_edit_save(str(test_file))
    assert result is None


def test_import():
    """Module should import without errors."""
    from core.engine.runtime.tools.git_safety import pre_edit_save

    assert callable(pre_edit_save)
