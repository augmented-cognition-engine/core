"""First-encounter regression tests.

The framing-reset text in three places must NOT drift back to 'minimal teaching
toy' language. These tests pin the load-bearing phrases from the spec."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


@pytest.mark.unit
def test_readme_opens_with_intelligence_builder_framing():
    """README leads with first intelligence value and retains trust boundaries below it."""
    readme = _read("README.md")
    head = " ".join(readme[:800].split())
    assert "ACE, the Intelligence Builder. Build intelligence, not infrastructure." in head
    assert "source-grounded briefing" in head
    assert "provenance, authority, durable state, and exact receipts" in head
    assert "## What ACE does" in readme
    assert "Connect → Map → Watch → Brief → Activate" in readme
    assert "Domain Pack JSON" in readme
    assert "### Two connected loops" in readme
    assert "Decision reasoning" in readme
    assert "Continuous intelligence" in readme
    assert "### What you can build" in readme
    assert "ACE supplies both the Intelligence Builder experience and the governed runtime" in readme
    assert "lean coordinating" in readme
    assert "not a literal ratio" in readme
    assert "Trustworthy intelligence is the feature" in readme
    assert "A nine-layer cognitive pipeline" in readme
    assert "Dynamic composition" in readme
    assert "Human ↔ ACE ↔ LLM" in readme
    assert "two-thirds of the intelligence" not in readme
    assert "minimal teaching" not in readme[:2000]  # the old framing is gone


@pytest.mark.unit
def test_flavor_docstring_carries_partnership_thesis():
    """extensions/reference/extension.py docstring must name the canonical extension role."""
    extension = _read("extensions/reference/extension.py")
    assert "the canonical ACE extension" in extension
    assert "partner team for product decisions" in extension
    assert "kill criteria" in extension


@pytest.mark.unit
def test_guide_opens_with_scaffold_first_octopus_framing():
    """docs/build-your-first-extension.md opens with the scaffold-first, 'new
    arm on the octopus' framing (promoted canonical tutorial, OSS Task 9).
    Supersedes the earlier zero-config-kernel opening pinned before the
    scaffold CLI existed."""
    guide = _read("docs/build-your-first-extension.md")
    head = guide[:800]
    assert "grow new arms on the octopus" in head
    assert "without forking it" in head
    assert "zero-config" not in head  # the superseded opening is gone
