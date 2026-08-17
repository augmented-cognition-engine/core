from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "docs" / "evidence" / "ace-1.1.0-local-release-candidate-v1.md"


def test_current_release_surfaces_are_110_without_rewriting_published_history() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert project["version"] == "1.1.0"
    assert "![local candidate 1.1.0]" in readme
    assert "python -m pip install ace-core==1.0.3" in readme
    assert "current published stable package and public-index install is `ace-core==1.0.3`" in readme
    assert "local `ace-core==1.1.0` **ACE 1.1 Code Intelligence release candidate**" in readme
    assert "Do not request\n1.1.0 from the public index" in readme
    assert "SurrealDB migrations (head: v177)" not in readme
    assert changelog.index("## 1.1.0") < changelog.index("## 1.0.3")
    assert "latest published release is [`ace-core` 1.0.3]" in roadmap
    assert "ACE 1.1.0 Code Intelligence has **passed for a local release candidate**" in roadmap


def test_release_candidate_evidence_is_public_safe_and_four_record_bounded() -> None:
    evidence = EVIDENCE_PATH.read_text(encoding="utf-8")
    index = (EVIDENCE_PATH.parent / "README.md").read_text(encoding="utf-8")

    assert "ace-1.1.0-local-release-candidate-v1.md" in index
    assert "/private/tmp" not in evidence
    assert "#194 remains open pending publication" in evidence
    assert "Release Spine Project" in evidence
    assert "remains **Now** pending publication" in evidence
    assert "candidate evidence only" in evidence
    assert "No record authorizes advancing 1.2 to Now" in evidence
    assert "create the exact `v1.1.0` tag" in evidence


def test_reference_adapter_compatibility_includes_110_without_rekeying() -> None:
    adapter = tomllib.loads(
        (ROOT / "adapters" / "reference_workspace_action" / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]

    assert adapter["version"] == "0.4.1"
    assert adapter["dependencies"] == ["ace-core>=0.8.0,<1.2"]


def test_capability_maturity_retains_public_10_and_bounds_local_11() -> None:
    maturity = (ROOT / "docs" / "capability-maturity.md").read_text(encoding="utf-8")

    assert "## Supported 1.0 contract" in maturity
    assert "version: `1.0.3` (current public release and public-index install)" in maturity
    assert "## ACE 1.1 Code Intelligence — local release candidate maturity" in maturity
    assert "Schema head is v179" in maturity
    assert "Issue #194 remains open" in maturity
    assert "Release Spine Project stays\nNow" in maturity
    assert "compiled static UI is\npackaged in both the Python wheel and source distribution" in maturity
    assert "included in both the Python wheel and sdist" in maturity
    assert "outside the Python wheel" not in maturity
    assert "not included in the Python wheel or sdist" not in maturity
