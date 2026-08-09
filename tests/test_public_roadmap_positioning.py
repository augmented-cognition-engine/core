from __future__ import annotations

from pathlib import Path

ROADMAP = (Path(__file__).resolve().parents[1] / "ROADMAP.md").read_text(encoding="utf-8")
ROADMAP_ONE_LINE = " ".join(ROADMAP.split())

# The 0.4.1 candidate/publication assertions below are a coordinated pre-release gate. The final
# post-publication reconciliation must update them together with ROADMAP.md and the candidate labels
# enforced by tests/test_evidence_index_integrity.py.


def test_current_release_and_active_milestone_are_not_conflated() -> None:
    assert "`ace-core` 0.4.0 is published on PyPI and GitHub" in ROADMAP
    assert ROADMAP.count("| 0.4.x | Governed Cognition | **Active** |") == 1
    assert "| 0.4.0 | Governed Cognition | **Delivered** |" not in ROADMAP
    assert "| 0.4.0 | Governed Cognition | **Now** |" not in ROADMAP
    assert "| 0.5.0 | Reasoning into Action | **Next** |" in ROADMAP


def test_governed_intelligence_pass_does_not_overstate_governed_cognition() -> None:
    assert "| GI1 | passed | Ship the governed Intelligence foundation as one installable" in ROADMAP
    assert "| GC1 | active | Make governed cognition an obvious supported" in ROADMAP
    assert "This does not close GC1, SI1–SI4, or any domain product" in ROADMAP


def test_gi1_claims_packaging_not_domain_neutrality() -> None:
    """GI1 is a packaging outcome. Neutrality is a falsification result and belongs to GI2.

    A published release proves the distribution installs and its contracts hold. It cannot
    prove the Intelligence layer is domain-neutral, because a single-domain abstraction
    always looks neutral from inside that domain. Only an independent second domain running
    the same lifecycle establishes that, so GI1 must not reclaim the words.
    """
    gi1 = next(line for line in ROADMAP.splitlines() if line.startswith("| GI1 |"))
    assert "domain-neutral Intelligence foundation" not in gi1
    assert "without embedding a vertical in Core" not in gi1
    assert "packaging, contract, and publication outcome" in gi1

    assert "| GI2 | not ready | Prove the Intelligence foundation is domain-neutral" in ROADMAP
    assert "Packaging evidence cannot establish neutrality" in ROADMAP


def test_core_intelligence_and_domain_boundaries_are_explicit() -> None:
    assert "**Core** owns cognition and control" in ROADMAP
    assert "**Intelligence** owns domain-neutral sensing and orientation" in ROADMAP
    assert "**Domain Packs and connectors** supply vocabulary and source access" in ROADMAP
    assert "without embedding their domain ontology in either layer" in ROADMAP


def test_external_domains_validate_the_shared_platform_in_parallel() -> None:
    assert "### Parallel domain validation" in ROADMAP
    assert "World Intelligence and Market Intelligence are the current validation targets" in ROADMAP
    assert "at least two materially different external domain packages" in ROADMAP_ONE_LINE


def test_041_candidate_is_not_conflated_with_a_public_release() -> None:
    """The 0.4.1 platform substrate narrative must not silently claim a public release.

    Only ace-core 0.4.0 has a published git tag, GitHub Release, and PyPI package. The 0.4.1
    work on main is implementation/evidence candidate only, and the World Intelligence source
    repository is public but untagged and unpublished. This must stay explicit so a reader
    cannot mistake "candidate evidence" for "shipped".
    """
    assert "ace-core` 0.4.1 implementation and evidence candidate" in ROADMAP_ONE_LINE
    assert (
        "only `ace-core` 0.4.0 has a git tag, a GitHub Release, and a published PyPI package"
        in ROADMAP_ONE_LINE
    )
    assert "`ace-core` 0.4.1 has none of the three yet" in ROADMAP_ONE_LINE
    assert "it carries no version tag, no GitHub Release, and no PyPI package" in ROADMAP_ONE_LINE

    forbidden = [
        "ace-core` 0.4.1 is published",
        "ace-core 0.4.1 is published",
        "World Intelligence is published",
        "domain-world-intelligence is published",
    ]
    for phrase in forbidden:
        assert phrase not in ROADMAP
        assert phrase not in ROADMAP_ONE_LINE


def test_platform_substrate_section_does_not_change_outcome_states() -> None:
    assert "### Governed Intelligence platform substrate" in ROADMAP
    assert "None of this candidate evidence moves `GI1`, `GI2`, `GC1`, or any other outcome state." in ROADMAP


def test_041_candidate_p2a_domain_pack_conformance_is_recorded() -> None:
    """P2A is consumer-repository conformance evidence, not a ported Core evidence record.

    This is a durable distinction, not pre-release prose: even after publication, P2A stays
    documented as World-repository conformance work (compiles through unchanged ace-core, seven
    conformance tests, five fail-closed mutations, co-installed with Market) rather than as a
    Core-side evidence file. Only the reproducibility caveat below is specific to this
    pre-release branch and should be replaced once the World repository ships.
    """
    assert "P2A" in ROADMAP
    assert "JSON-only World Domain Pack" in ROADMAP
    assert "seven conformance tests" in ROADMAP
    assert "five fail-closed mutations" in ROADMAP
    assert "co-installation alongside the Market" in ROADMAP
    assert "no separate Core evidence record was ported into this archive for it" in ROADMAP_ONE_LINE

    # Pre-release-only: replace in the final post-publication reconciliation commit.
    assert (
        "it remains non-publicly reproducible until the World repository is tagged, released on GitHub, and packaged"
        in ROADMAP_ONE_LINE
    )


def test_041_candidate_publication_gate_is_exact_and_gi2_stays_open_until_it_passes() -> None:
    """The publication gate must be an exact, checkable sequence, not vague "remaining step" prose."""
    assert "The exact gate before this evidence can support a" in ROADMAP
    assert "merge the pending Core evidence" in ROADMAP
    assert "tag, GitHub-Release, and publish to PyPI `ace-core` 0.4.1" in ROADMAP_ONE_LINE
    assert (
        "tag, GitHub-Release, and publish to PyPI the Domain-World-Intelligence `World` package"
        in ROADMAP_ONE_LINE
    )
    assert "re-run the clean-install two-domain journey end to end" in ROADMAP
    assert "`GI2` stays `not ready` until that final reproduction passes" in ROADMAP_ONE_LINE

    assert "is the only remaining step before this evidence can support a public claim" not in ROADMAP_ONE_LINE
