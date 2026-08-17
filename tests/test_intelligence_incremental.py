# tests/test_intelligence_incremental.py
"""Tests for incremental graph updates."""

import os
import tempfile
from copy import deepcopy

import pytest

from core.engine.intelligence import graph_builder as graph_builder_module
from core.engine.intelligence.graph_builder import GraphBuilder

_UNPARSEABLE = b"# unparseable-marker"


def _exact_state(builder):
    """Capture files/symbols/imports plus every node and edge attribute."""
    return (
        deepcopy(builder.export_phase1_state()),
        deepcopy(dict(builder.graph.nodes(data=True))),
        deepcopy({(source, target): data for source, target, data in builder.graph.edges(data=True)}),
    )


def _selective_parse_failure(monkeypatch):
    """Fail only for staged content carrying the unparseable marker."""
    original = graph_builder_module.parse_file

    def parse(content, lang):
        if _UNPARSEABLE in content:
            raise ValueError("staged parse failure")
        return original(content, lang)

    monkeypatch.setattr(graph_builder_module, "parse_file", parse)


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


def test_phase1_state_reopens_exact_graph_without_rescan():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    reopened = GraphBuilder.from_phase1_state(d, builder.export_phase1_state())

    assert reopened.export_phase1_state() == builder.export_phase1_state()
    assert set(reopened.graph.nodes) == set(builder.graph.nodes)
    assert set(reopened.graph.edges) == set(builder.graph.edges)


def test_incremental_replaces_import_records_edges_and_symbol_nodes():
    d = _test_repo()
    with open(os.path.join(d, "other.py"), "w") as f:
        f.write("class Other:\n    pass\n")
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    assert ("services.py", "models.py") in builder.graph.edges
    assert "services.py::get_user" in builder.graph

    with open(os.path.join(d, "services.py"), "w") as f:
        f.write("from other import Other\n\ndef get_other():\n    return Other()\n")
    builder.incremental_update(["services.py"])

    assert ("services.py", "models.py") not in builder.graph.edges
    assert ("services.py", "other.py") in builder.graph.edges
    assert "services.py::get_user" not in builder.graph
    assert "services.py::get_other" in builder.graph
    assert [item["module"] for item in builder.get_imports() if item["from_file"] == "services.py"] == ["other"]


def test_incremental_rejects_repository_escape():
    builder = GraphBuilder(_test_repo())
    builder.phase1_treesitter()

    try:
        builder.incremental_update(["../outside.py"])
    except ValueError as exc:
        assert "escapes repository" in str(exc)
    else:
        raise AssertionError("repository escape was accepted")


def test_incremental_parse_failure_preserves_prior_state(monkeypatch):
    builder = GraphBuilder(_test_repo())
    builder.phase1_treesitter()
    prior_state = deepcopy(builder.export_phase1_state())
    prior_nodes = deepcopy(dict(builder.graph.nodes(data=True)))
    prior_edges = deepcopy(dict(((source, target), data) for source, target, data in builder.graph.edges(data=True)))
    monkeypatch.setattr(
        "core.engine.intelligence.graph_builder.parse_file", lambda *_args: (_ for _ in ()).throw(ValueError("bad"))
    )

    assert builder.incremental_update(["services.py"])["updated"] == 0
    assert builder.export_phase1_state() == prior_state
    assert dict(builder.graph.nodes(data=True)) == prior_nodes
    assert dict(((source, target), data) for source, target, data in builder.graph.edges(data=True)) == prior_edges


def test_incremental_preserves_lsp_metadata_on_rough_import_edge():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    builder.graph["services.py"]["models.py"]["type"] = "lsp_reference"
    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n")

    builder.incremental_update(["models.py"])

    assert builder.graph["services.py"]["models.py"]["type"] == "lsp_reference"


def test_incremental_rejects_symlink_escape(tmp_path):
    d = _test_repo()
    outside = tmp_path / "outside.py"
    outside.write_text("def outside():\n    pass\n", encoding="utf-8")
    os.symlink(outside, os.path.join(d, "link.py"))
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    with pytest.raises(ValueError, match="escapes repository"):
        builder.incremental_update(["link.py"])


def test_incremental_batch_is_atomic_when_a_later_path_fails_to_parse(monkeypatch):
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    builder.graph["services.py"]["models.py"]["lsp"] = {"kind": "reference", "hits": [1, 2]}
    prior = _exact_state(builder)

    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n\nclass Renamed:\n    pass\n")
    with open(os.path.join(d, "services.py"), "w") as f:
        f.write("# unparseable-marker\nfrom models import User\n")
    _selective_parse_failure(monkeypatch)

    assert builder.incremental_update(["models.py", "services.py"]) == {"updated": 0, "symbols_added": 0}
    assert _exact_state(builder) == prior
    assert not any(item["name"] == "Renamed" for item in builder.get_symbols())
    assert builder.graph["services.py"]["models.py"]["lsp"] == {"kind": "reference", "hits": [1, 2]}


def test_incremental_batch_escape_raises_only_after_exact_rollback():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    prior = _exact_state(builder)

    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n\nclass Renamed:\n    pass\n")

    with pytest.raises(ValueError, match="escapes repository"):
        builder.incremental_update(["models.py", "../outside.py"])

    assert _exact_state(builder) == prior
    assert not any(item["name"] == "Renamed" for item in builder.get_symbols())


def test_incremental_batch_restores_a_staged_deletion_when_a_later_path_fails(monkeypatch):
    d = _test_repo()
    with open(os.path.join(d, "other.py"), "w") as f:
        f.write("class Other:\n    pass\n")
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    prior = _exact_state(builder)

    os.unlink(os.path.join(d, "services.py"))
    with open(os.path.join(d, "other.py"), "w") as f:
        f.write("# unparseable-marker\nclass Other:\n    pass\n")
    _selective_parse_failure(monkeypatch)

    assert builder.incremental_update(["services.py", "other.py"]) == {"updated": 0, "symbols_added": 0}
    assert _exact_state(builder) == prior
    assert "services.py" in [item["path"] for item in builder.get_files()]
    assert "services.py" in builder.graph


def test_incremental_batch_applies_every_valid_path_exactly_once():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    with open(os.path.join(d, "models.py"), "w") as f:
        f.write("class User:\n    pass\n\nclass Renamed:\n    pass\n")
    with open(os.path.join(d, "views.py"), "w") as f:
        f.write("from models import Renamed\n\ndef index():\n    pass\n")

    stats = builder.incremental_update(["models.py", "./models.py", "views.py"])

    assert stats["updated"] == 2
    assert stats["symbols_added"] == 3
    assert [item["path"] for item in builder.get_files()].count("models.py") == 1
    assert ("views.py", "models.py") in builder.graph.edges


def test_walk_files_never_sizes_or_opens_a_symlink_to_outside_source(tmp_path):
    d = _test_repo()
    outside = tmp_path / "outside_secret.py"
    outside.write_text("def outside_secret():\n    pass\n", encoding="utf-8")
    os.symlink(outside, os.path.join(d, "linked.py"))

    builder = GraphBuilder(d)
    builder.phase1_treesitter()

    assert "linked.py" not in [item["path"] for item in builder.get_files()]
    assert "linked.py" not in builder.graph
    assert not any(item["name"] == "outside_secret" for item in builder.get_symbols())


def test_phase1_state_is_deeply_detached():
    d = _test_repo()
    builder = GraphBuilder(d)
    builder.phase1_treesitter()
    exported = builder.export_phase1_state()
    exported["symbols"][0]["name"] = "mutated"
    assert builder.get_symbols()[0]["name"] != "mutated"

    reopened = GraphBuilder.from_phase1_state(d, builder.export_phase1_state())
    restored = reopened.export_phase1_state()
    restored["imports"][0]["module"] = "mutated"
    assert reopened.get_imports()[0]["module"] != "mutated"
