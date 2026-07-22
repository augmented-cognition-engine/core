from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name

import ace
import ace_mcp_client
from core.engine.version import VERSION
from extensions.reference.extension import ProductExtension
from scripts import release_inventory

ROOT = Path(__file__).resolve().parents[1]


def test_distribution_import_cli_and_version_identities() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["name"] == "ace-core"
    assert project["version"] == ace.__version__ == ace_mcp_client.__version__ == VERSION == "0.1.2"
    assert ProductExtension.version == project["version"]
    assert project["scripts"]["ace"] == "core.engine.cli.main:cli"


def test_package_copy_and_public_links_are_release_ready() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert project["description"] == ("Self-hosted reasoning that turns product decisions into durable recommendations")
    assert project["urls"]["Documentation"] == "https://github.com/augmented-cognition-engine/core#readme"
    assert project["urls"]["Changelog"].endswith("/blob/main/CHANGELOG.md")
    relative_links = [
        target for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", readme) if not target.startswith(("https://", "#"))
    ]
    assert relative_links == []


def test_release_workflow_defaults_to_and_guards_current_version() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")

    assert "default: v0.1.2" in workflow
    assert "Validate release tag matches package version" in workflow
    assert 'if [ "$RELEASE_TAG" != "v$package_version" ]' in workflow


def test_docker_image_includes_public_cli_package() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY ace/ ace/" in dockerfile


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
