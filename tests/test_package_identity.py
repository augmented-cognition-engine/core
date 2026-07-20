from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name

import ace
from scripts import release_inventory

ROOT = Path(__file__).resolve().parents[1]


def test_distribution_import_cli_and_version_identities() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["name"] == "ace-core"
    assert project["version"] == ace.__version__ == "0.1.0"
    assert project["scripts"]["ace"] == "core.engine.cli.main:cli"


def test_lock_tracks_the_distribution_identity() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    local = [package for package in lock["package"] if package.get("source") == {"editable": "."}]

    assert [package["name"] for package in local] == ["ace-core"]


def test_release_inventory_reads_ace_core_requirements(monkeypatch) -> None:
    requested: list[str] = []

    def requires(name: str) -> list[str]:
        requested.append(name)
        return ["httpx>=0.27"]

    monkeypatch.setattr(release_inventory.metadata, "requires", requires)

    assert release_inventory._direct_dependencies() == {canonicalize_name("httpx")}
    assert requested == ["ace-core"]


def test_installed_documentation_paths_do_not_collide() -> None:
    data_files = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"][
        "data-files"
    ]

    assert "README.md" in data_files["share/doc/ace"]
    assert "ROADMAP.md" in data_files["share/doc/ace"]
    assert "docs/*.md" in data_files["share/doc/ace/docs"]
    assert all("launch" not in path for paths in data_files.values() for path in paths)
