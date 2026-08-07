from __future__ import annotations

from pathlib import Path

ROADMAP = (Path(__file__).resolve().parents[1] / "ROADMAP.md").read_text(encoding="utf-8")
ROADMAP_ONE_LINE = " ".join(ROADMAP.split())


def test_current_release_and_active_milestone_are_not_conflated() -> None:
    assert "`ace-core` 0.4.0 is published on PyPI and GitHub" in ROADMAP
    assert ROADMAP.count("| 0.4.x | Governed Cognition | **Active** |") == 1
    assert "| 0.4.0 | Governed Cognition | **Delivered** |" not in ROADMAP
    assert "| 0.4.0 | Governed Cognition | **Now** |" not in ROADMAP
    assert "| 0.5.0 | Reasoning into Action | **Next** |" in ROADMAP


def test_governed_intelligence_pass_does_not_overstate_governed_cognition() -> None:
    assert "| GI1 | passed | Ship the governed, domain-neutral Intelligence foundation" in ROADMAP
    assert "| GC1 | active | Make governed cognition an obvious supported" in ROADMAP
    assert "This does not close GC1, SI1–SI4, or any domain product" in ROADMAP


def test_core_intelligence_and_domain_boundaries_are_explicit() -> None:
    assert "**Core** owns cognition and control" in ROADMAP
    assert "**Intelligence** owns domain-neutral sensing and orientation" in ROADMAP
    assert "**Domain Packs and connectors** supply vocabulary and source access" in ROADMAP
    assert "without embedding their domain ontology in either layer" in ROADMAP


def test_external_domains_validate_the_shared_platform_in_parallel() -> None:
    assert "### Parallel domain validation" in ROADMAP
    assert "World Intelligence and Market Intelligence are the current validation targets" in ROADMAP
    assert "at least two materially different external domain packages" in ROADMAP_ONE_LINE
