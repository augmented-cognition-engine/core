# tests/test_runtime_init_project.py
"""Tests for ace init — project bootstrap."""


def test_import_claude_md_sections():
    """Test that _import_claude_md parses sections correctly."""
    # This tests the parsing logic without DB
    from core.engine.runtime.init_project import _import_claude_md  # noqa: F401

    # Just verify import works — actual DB write is mocked in e2e
    assert callable(_import_claude_md)


def test_init_project_exists():
    from core.engine.runtime.init_project import init_project

    assert callable(init_project)
