"""First-encounter regression tests.

The framing-reset text in three places must NOT drift back to 'minimal teaching
toy' language. These tests pin the load-bearing phrases from the spec."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


@pytest.mark.unit
def test_readme_opens_with_partner_team_framing():
    """README's opening must establish the thesis rung of the builder's
    ladder (OSS Task 10): partner-team framing, the thesis line, and the
    octopus anatomy. Supersedes the earlier worked-example opening pinned
    before the ladder restructure."""
    readme = _read("README.md")
    head = readme[:800]
    # The launch hero leads with accurate partner-team framing and the octopus
    # section explicitly treats the biology as inspiration rather than a literal
    # code or intelligence ratio.
    assert "partner team for thinking" in head
    assert "Bring the problem. ACE assembles the thinking." in head
    assert "lean coordinating" in readme
    assert "not a literal ratio" in readme
    assert "The architecture is the feature" in readme
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
