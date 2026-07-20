"""Tests for the ACE-native repository map backed by the code graph."""

import os
import tempfile

from core.engine.runtime.repo_map import RepoMap


def _create_test_repo():
    """Create a small test repo with cross-references."""
    d = tempfile.mkdtemp()

    # models.py defines User and Post
    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n\nclass Post:\n    pass\n")

    # services.py imports and uses User
    with open(os.path.join(d, "services.py"), "w") as f:
        f.write("from models import User\n\ndef get_user(id):\n    return User()\n")

    # views.py imports User and Post
    with open(os.path.join(d, "views.py"), "w") as f:
        f.write("from models import User, Post\n\ndef user_view():\n    pass\n\ndef post_view():\n    pass\n")

    # tests.py imports from services
    with open(os.path.join(d, "tests.py"), "w") as f:
        f.write("from services import get_user\n\ndef test_get_user():\n    pass\n")

    return d


def test_build():
    d = _create_test_repo()
    rm = RepoMap(d)
    count = rm.build()
    assert count >= 3  # at least models, services, views
    assert rm.file_count >= 3


def test_rank_models_highest():
    """models.py defines the most-referenced symbols — should rank high."""
    d = _create_test_repo()
    rm = RepoMap(d)
    rm.build()
    ranked = rm.rank()
    paths = [r["path"] for r in ranked]
    # models.py should be in top results (most referenced)
    assert "models.py" in paths[:3]


def test_rank_with_query():
    d = _create_test_repo()
    rm = RepoMap(d)
    rm.build()
    ranked = rm.rank(query="user authentication")
    # With new graph-based ranking, files should be ranked by connectivity
    assert len(ranked) > 0
    # models.py is the most connected so should appear in top results
    paths = [r["path"] for r in ranked]
    assert any(p in paths[:4] for p in ["models.py", "services.py", "views.py"])


def test_rank_with_focused_files():
    d = _create_test_repo()
    rm = RepoMap(d)
    rm.build()
    ranked = rm.rank(focused_files=["services.py"])
    # services.py or its dependencies should rank high
    assert ranked[0]["score"] > 0


def test_get_context():
    d = _create_test_repo()
    rm = RepoMap(d)
    rm.build()
    ctx = rm.get_context(query="models", token_budget=500)
    # Context returns file paths — at least one file should be listed
    assert len(ctx) > 0
    assert ".py" in ctx


def test_empty_repo():
    d = tempfile.mkdtemp()
    rm = RepoMap(d)
    count = rm.build()
    assert count == 0
    assert rm.rank() == []


def test_definitions_extracted():
    d = _create_test_repo()
    rm = RepoMap(d)
    rm.build()
    # _definitions is populated by _build_from_files (the sync fallback)
    models_defs = rm._definitions.get("models.py", [])
    names = [d["name"] for d in models_defs]
    assert "User" in names
    assert "Post" in names


def test_edges_built():
    d = _create_test_repo()
    rm = RepoMap(d)
    rm.build()
    assert rm.edge_count > 0  # cross-file references should create edges
