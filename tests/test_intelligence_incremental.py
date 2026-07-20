# tests/test_intelligence_incremental.py
"""Tests for incremental graph updates."""

import os
import tempfile

from core.engine.intelligence.graph_builder import GraphBuilder


def _test_repo():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n\nclass Post:\n    pass\n")
    with open(os.path.join(d, "services.py"), "w") as f:
        f.write("from models import User\n\ndef get_user():\n    return User()\n")
    return d


def test_incremental_update_modified_file():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    initial_symbols = len(builder.get_symbols())

    # Add a new class to models.py
    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n\nclass Post:\n    pass\n\nclass Comment:\n    pass\n")

    stats = builder.incremental_update(["models.py"])
    assert stats["updated"] == 1
    assert len(builder.get_symbols()) > initial_symbols


def test_incremental_update_deleted_file():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    initial_nodes = builder.graph.number_of_nodes()

    os.unlink(os.path.join(d, "services.py"))
    stats = builder.incremental_update(["services.py"])
    # File was deleted — should be removed from graph
    assert builder.graph.number_of_nodes() < initial_nodes


def test_incremental_update_new_file():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    # Create a new file
    with open(os.path.join(d, "views.py"), "w") as f:
        f.write("from models import User, Post\n\ndef index():\n    pass\n")

    stats = builder.incremental_update(["views.py"])
    assert stats["updated"] == 1
    assert "views.py" in [f["path"] for f in builder.get_files()]


def test_incremental_preserves_other_files():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    # Modify one file
    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n")

    builder.incremental_update(["models.py"])

    # services.py should still be in the graph
    assert "services.py" in [f["path"] for f in builder.get_files()]
