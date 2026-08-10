from __future__ import annotations

from pathlib import Path

ROADMAP = (Path(__file__).resolve().parents[1] / "ROADMAP.md").read_text(encoding="utf-8")
ROADMAP_ONE_LINE = " ".join(ROADMAP.split())

# The 0.5.0 checkpoint assertions are the coordinated T1/B1 closeout gate. Historical 0.4.1 GI2,
# 0.4.2 builder-surface, 0.4.4 GC1, and P1/P2 identities remain exact point-in-time evidence. Keep
# these aligned with test_evidence_index_integrity.py.


def test_current_release_and_passed_milestone_are_not_conflated() -> None:
    assert "`ace-core` 0.5.0 is published on PyPI and GitHub" in ROADMAP
    assert ROADMAP.count("| 0.4.x | Governed Cognition | **Passed** |") == 1
    assert "| 0.4.0 | Governed Cognition | **Delivered** |" not in ROADMAP
    assert "| 0.4.0 | Governed Cognition | **Now** |" not in ROADMAP
    assert "| 0.5.0 | Reasoning into Action | **Passed** |" in ROADMAP
    assert "| 0.6.0 | Measured Intelligence | **Next** |" in ROADMAP


def test_050_public_external_consumer_closes_t1_and_b1_with_bounded_topology() -> None:
    assert "[0.5.0 GitHub Release]" in ROADMAP
    assert "public [`ace-core==0.5.0`]" in ROADMAP
    assert "[Reasoning into Action release evidence]" in ROADMAP
    assert "| T1 | passed |" in ROADMAP
    assert "| B1 | passed |" in ROADMAP
    assert "checkout-free environment" in ROADMAP_ONE_LINE
    assert "single-host, trusted-adapter topology" in ROADMAP_ONE_LINE
    assert "does not claim unrestricted autonomy" in ROADMAP_ONE_LINE


def test_044_public_external_consumer_closes_gc1_without_rewriting_042() -> None:
    assert "[0.4.4 GitHub Release]" in ROADMAP
    assert "public `ace-core==0.4.4` package" in ROADMAP_ONE_LINE
    assert "[GC1 public external-consumer evidence]" in ROADMAP
    assert "point-in-time receipt for 0.4.2" in ROADMAP_ONE_LINE
    assert "independent Market Intelligence consumer" in ROADMAP_ONE_LINE
    assert "**GC1** is therefore passed in 0.4.x" in ROADMAP_ONE_LINE


def test_governed_intelligence_substrate_is_not_retroactively_made_gc1_evidence() -> None:
    assert "| GI1 | passed | Ship the governed Intelligence foundation as one installable" in ROADMAP
    assert "| GC1 | passed | Make governed cognition an obvious supported" in ROADMAP
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

    assert "| GI2 | passed | Prove the Intelligence foundation is domain-neutral" in ROADMAP
    assert "Domain neutrality remains a falsification result rather than a packaging property" in ROADMAP
    assert "This is domain-neutral substrate evidence, not SI1–SI4 completion" in ROADMAP


def test_core_intelligence_and_domain_boundaries_are_explicit() -> None:
    assert "**Core** owns cognition and control" in ROADMAP
    assert "**Intelligence** owns domain-neutral sensing and orientation" in ROADMAP
    assert "**Domain Packs and connectors** supply vocabulary and source access" in ROADMAP
    assert "without embedding their domain ontology in either layer" in ROADMAP


def test_external_domains_validate_the_shared_platform_in_parallel() -> None:
    assert "### Parallel domain validation" in ROADMAP
    assert "World Intelligence and Market Intelligence are the current validation targets" in ROADMAP
    assert "at least two materially different external domain packages" in ROADMAP_ONE_LINE


def test_041_and_both_domain_falsification_packages_are_public() -> None:
    """The public GI2 claim must name exact independently installable release identities."""
    assert "[0.4.1 GitHub Release]" in ROADMAP
    assert "public `ace-core==0.4.1` package" in ROADMAP_ONE_LINE
    assert "`ace-domain-world-intelligence==0.8.0`" in ROADMAP_ONE_LINE
    assert "`ace-domain-market-intelligence==0.6.0`" in ROADMAP_ONE_LINE
    assert "Core 0.4.1, World Intelligence 0.8.0, and Market Intelligence 0.6.0 artifacts" in ROADMAP_ONE_LINE


def test_platform_substrate_section_preserves_gi2_and_acknowledges_later_gc1_closeout() -> None:
    assert "### Governed Intelligence platform substrate" in ROADMAP
    assert "GI2 is therefore reconciled to `passed`" in ROADMAP
    assert "GI1 and GC1 are passed" in ROADMAP
    assert "SI1–SI4 remain bounded future outcomes" in ROADMAP_ONE_LINE


def test_041_public_p2a_domain_pack_conformance_is_recorded() -> None:
    """P2A is consumer-repository conformance evidence, not a ported Core evidence record.

    This is a durable distinction, not pre-release prose: even after publication, P2A stays
    documented as World-repository conformance work (compiles through unchanged ace-core, seven
    conformance tests, five fail-closed mutations, co-installed with Market) rather than as a
    Core-side evidence file. Its public tag and package now make the consumer proof independently
    reproducible without changing which repository owns that proof.
    """
    assert "P2A" in ROADMAP
    assert "JSON-only World Domain Pack" in ROADMAP
    assert "seven conformance tests" in ROADMAP
    assert "five fail-closed mutations" in ROADMAP
    assert "co-installation alongside the Market" in ROADMAP
    assert "no separate Core evidence record was ported into this archive for it" in ROADMAP_ONE_LINE

    assert (
        "Its public `v0.8.0` tag and package now make that consumer proof independently reproducible"
        in ROADMAP_ONE_LINE
    )


def test_041_publication_gate_is_complete_and_bounded() -> None:
    """GI2 closes only after the release and cross-domain reproduction sequence has passed."""
    assert "Their former publication gate has now passed" in ROADMAP_ONE_LINE
    assert "Core 0.4.1, World 0.8.0, and Market 0.6.0 are public" in ROADMAP_ONE_LINE
    assert "the tagged World conformance suite passes" in ROADMAP_ONE_LINE
    assert "clean public-index two-domain activation and retirement-isolation journey passes" in ROADMAP_ONE_LINE
    assert "does not establish hostile-code isolation" in ROADMAP_ONE_LINE

    assert "| GC1 | passed |" in ROADMAP
    for outcome in ("SI1", "SI2", "SI3", "SI4"):
        assert f"| {outcome} | not ready |" in ROADMAP
