from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name

import ace
import ace_mcp_client
from core.engine.grounded_state import belief_evaluation, candidate_evaluation
from core.engine.version import VERSION
from extensions.reference.extension import ProductExtension
from scripts import release_inventory

ROOT = Path(__file__).resolve().parents[1]


def test_distribution_import_cli_and_version_identities() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["name"] == "ace-core"
    assert project["version"] == ace.__version__ == ace_mcp_client.__version__ == VERSION == "1.2.3"
    assert "Development Status :: 5 - Production/Stable" in project["classifiers"]
    assert ProductExtension.version == project["version"]
    assert project["scripts"]["ace"] == "core.engine.cli.main:cli"
    assert "aiohttp>=3.14.3" in project["dependencies"]
    assert "cryptography>=50.0.0" in project["dependencies"]


def test_package_copy_and_public_links_are_release_ready() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert project["description"] == "Open Intelligence Operating System with a guided Intelligence Builder"
    assert project["urls"]["Documentation"] == "https://github.com/augmented-cognition-engine/core#readme"
    assert project["urls"]["Changelog"].endswith("/blob/main/CHANGELOG.md")
    relative_links = [
        target for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", readme) if not target.startswith(("https://", "#"))
    ]
    assert relative_links == []


def test_release_workflow_defaults_to_and_guards_current_version() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")

    assert "default: v1.2.3" in workflow
    assert "Validate release tag matches package version" in workflow
    assert 'if [ "$RELEASE_TAG" != "v$package_version" ]' in workflow
    assert "ace-core-python-distributions" in workflow
    assert "reference-workspace-action-distributions" in workflow
    assert "build==1.5.0 setuptools==83.0.0 twine==7.0.0" in workflow
    assert "python -m build --outdir dist/reference-adapter adapters/reference_workspace_action" in workflow
    assert "from build_backend import _normalize_sdist" in workflow
    assert "packages-dir: dist/core/" in workflow
    assert 'gh release upload "$RELEASE_TAG"' in workflow

    # PI11: the widened-envelope adapter re-release and the public bundle,
    # pack, and local-source adapter family attach to the same GitHub Release.
    assert 'if [ "$adapter_version" != "0.5.0" ]' in workflow
    assert 'assert project["dependencies"] == ["ace-core>=0.8.0,<2"]' in workflow
    assert "Validate attached artifacts admit the released core" in workflow
    assert "for adapter in adapters/local_*/" in workflow
    assert "python -m build --outdir dist/pack domain_packs/personal_intelligence" in workflow
    assert "python -m build --outdir dist/bundle solution_bundles/personal_intelligence" in workflow
    assert "local-source-adapter-distributions" in workflow
    assert "personal-intelligence-pack-distributions" in workflow
    assert "personal-intelligence-bundle-distributions" in workflow
    assert "dist/reference-adapter/* dist/local-adapters/* dist/pack/* dist/bundle/*" in workflow

    # 1.2.1 (#252): artifacts that cannot start the journey must never publish.
    assert "Journey-start smoke from built artifacts" in workflow
    assert "ace --help" in workflow
    assert "intelligence_onboarding_profile:personal" in workflow
    assert "load_installed_intelligence_build_planners" in workflow
    assert "resolve_intelligence_build_planner" in workflow


def test_docker_image_includes_public_cli_package() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY ace/ ace/" in dockerfile
    assert "README.md ROADMAP.md VISION.md MANIFESTO.md" in dockerfile
    assert "ARG ACE_VERSION=1.2.3" in dockerfile
    assert 'org.opencontainers.image.version="${ACE_VERSION}"' in dockerfile
    assert "uv sync --frozen --no-dev --no-editable --no-cache" in dockerfile

    compose = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count('ACE_VERSION: "1.2.3"') == 3
    assert compose.count('org.opencontainers.image.version: "1.2.3"') == 2


def test_lock_tracks_the_distribution_identity() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    local = [package for package in lock["package"] if package.get("source") == {"editable": "."}]

    assert [package["name"] for package in local] == ["ace-core"]
    assert [package["version"] for package in local] == ["1.2.3"]


def test_release_inventory_reads_ace_core_requirements(monkeypatch) -> None:
    requested: list[str] = []

    def requires(name: str) -> list[str]:
        requested.append(name)
        return ["httpx>=0.27"]

    monkeypatch.setattr(release_inventory.metadata, "requires", requires)

    assert release_inventory._direct_dependencies() == {canonicalize_name("httpx")}
    assert requested == ["ace-core"]


def test_release_inventory_records_installed_ace_core_version(monkeypatch) -> None:
    monkeypatch.setattr(release_inventory.metadata, "distributions", lambda: [])
    monkeypatch.setattr(release_inventory.metadata, "requires", lambda _name: [])
    monkeypatch.setattr(release_inventory.metadata, "version", lambda name: "0.3.1" if name == "ace-core" else "")

    assert release_inventory.build_inventory()["ace_core_version"] == "0.3.1"


def test_installed_documentation_paths_do_not_collide() -> None:
    data_files = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"][
        "data-files"
    ]

    assert "README.md" in data_files["share/doc/ace"]
    assert "ROADMAP.md" in data_files["share/doc/ace"]
    assert "VISION.md" in data_files["share/doc/ace"]
    assert "MANIFESTO.md" in data_files["share/doc/ace"]
    assert "docs/*.md" in data_files["share/doc/ace/docs"]
    assert "docs/evidence/*.md" in data_files["share/doc/ace/docs/evidence"]
    assert "docs/design/*.md" in data_files["share/doc/ace/docs/design"]
    assert all("launch" not in path for paths in data_files.values() for path in paths)


def test_release_archives_exclude_host_specific_k1_k3_raw_trials() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "prune evaluations/results/state_engine_k1_k3_raw" in manifest
    assert "evaluations/results/state_engine_k1_k3_raw" in dockerignore


def test_frozen_state_engine_corpus_is_packaged_for_checkout_free_smoke_runs() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_corpus = ROOT / "core/engine/grounded_state/fixtures/temporal_reference_candidate_v1.json"
    review_corpus = ROOT / "tests/fixtures/grounded_state/temporal_reference_candidate_v1.json"

    assert runtime_corpus.read_bytes() == review_corpus.read_bytes()
    assert belief_evaluation.DEFAULT_CORPUS == runtime_corpus
    assert candidate_evaluation.DEFAULT_CORPUS == runtime_corpus
    assert "fixtures/*.json" in project["tool"]["setuptools"]["package-data"]["core.engine.grounded_state"]


def test_domain_pack_schemas_are_declared_as_wheel_package_data() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "intelligence/schemas/*.json" in project["tool"]["setuptools"]["package-data"]["ace"]
    assert (ROOT / "ace/intelligence/schemas/domain-pack-contracts-v1.json").is_file()
    assert (ROOT / "ace/intelligence/schemas/domain-pack-manifest-v1.schema.json").is_file()
