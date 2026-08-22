from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "docs" / "evidence" / "ace-1.2.0-local-release-candidate-v1.md"


def test_current_release_surfaces_are_120_without_rewriting_published_history() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    package = (ROOT / "ace" / "__init__.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert project["version"] == "1.2.3"
    assert '__version__ = "1.2.3"' in package
    assert "![published version 1.2.3]" in readme
    assert "python -m pip install ace-core==1.2.3" in readme
    assert "current published stable package and public-index install is `ace-core==1.2.3`" in readme
    assert "**Stable 1.2.3**" in readme
    assert "1.2.3 is the recommended" in " ".join(readme.split())
    assert (
        changelog.index("## 1.2.3")
        < changelog.index("## 1.2.2")
        < changelog.index("## 1.2.1")
        < changelog.index("## 1.2.0")
        < changelog.index("## 1.1.0")
    )
    assert "## Unreleased" not in changelog
    assert "latest published release is [`ace-core` 1.2.3]" in roadmap
    # Published history stays intact: the 1.1 sections and records remain.
    assert "## 1.1.0" in changelog
    assert (ROOT / "docs" / "evidence" / "ace-1.1.0-public-release-v1.md").exists()


def test_release_candidate_evidence_record_exists_and_stays_honest() -> None:
    evidence = EVIDENCE_PATH.read_text(encoding="utf-8")
    index = (EVIDENCE_PATH.parent / "README.md").read_text(encoding="utf-8")

    assert "ace-1.2.0-local-release-candidate-v1.md" in index
    assert "not published" in evidence
    assert "does not close issue #195" in evidence
    assert "J1–J10" in evidence
    assert "create the exact `v1.2.0` tag" in evidence
    assert "/private/tmp" not in evidence


def test_getting_started_is_checkout_free_and_current() -> None:
    # D1 from the 1.2.0 acceptance run: the public getting-started path
    # described 1.0.3 and required a git clone the acceptance rules forbid.
    guide = (ROOT / "docs" / "getting-started.md").read_text(encoding="utf-8")
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert "1.0.3" not in guide
    quickstart = guide.split("## Contributor", 1)[0]
    assert "git clone" not in quickstart, "the supported quickstart must not require a source checkout"
    assert "pip install ace-core==1.2" in quickstart
    assert "ace-personal-intelligence-bundle" in guide
    assert "ACE_API_PORT" in guide
    assert "ACE_SURREAL_HOST_PORT" in guide
    assert "install ACE 1.0.3" not in index


def test_release_workflow_defaults_to_the_new_tag() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    assert "default: v1.2.3" in workflow
    assert "default: v1.1.0" not in workflow


def test_docker_surfaces_are_120() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "ARG ACE_VERSION=1.2.3" in dockerfile
    assert compose.count('ACE_VERSION: "1.2.3"') == 3
    assert compose.count('org.opencontainers.image.version: "1.2.3"') == 2


def test_capability_maturity_publishes_bounded_12() -> None:
    maturity = (ROOT / "docs" / "capability-maturity.md").read_text(encoding="utf-8")
    assert "## Supported 1.2 contract" in maturity
    assert "version: `1.2.3` (current public release and public-index install)" in maturity
    assert "Personal Intelligence" in maturity
