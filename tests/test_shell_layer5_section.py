# tests/test_shell_layer5_section.py
"""Tests for ShellComposer._build_layer5_section — the L5 prompt-rendering
half of decision:lv6stu70piemfwypde2e. Pure-function tests against the
section builder; no DB or LLM needed.

Spec: docs/superpowers/specs/2026-05-14-layer5-context-assembly-design.md §6.3
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.engine.orchestration.shell import ShellComposer
from core.engine.orchestrator.context import TieredDecision


def _td(
    decision_id: str,
    tier: str,
    title: str = "t",
    rationale: str = "r",
    outcome: str | None = "accepted",
    relevance_score: float = 0.9,
    caps: list[str] | None = None,
) -> TieredDecision:
    return TieredDecision(
        decision_id=decision_id,
        title=title,
        rationale=rationale,
        decision_type="architecture",
        discipline_hint=None,
        affected_capabilities=caps or [],
        created_at=datetime.now(timezone.utc),
        tier=tier,  # type: ignore[arg-type]
        relevance_score=relevance_score,
        outcome=outcome,  # type: ignore[arg-type]
        status=None,
        affected_capabilities_confidence=None,
    )


# -----------------------------------------------------------------------------
# Empty paths — regression-critical
# -----------------------------------------------------------------------------


def test_empty_classification_renders_nothing():
    """No L5 keys at all → empty string (composer behavior identical to pre-L5)."""
    sc = ShellComposer()
    assert sc._build_layer5_section({}) == ""


def test_empty_decisions_no_degraded_renders_nothing():
    """Cold-start product (no decisions, no degradation) → empty string."""
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [],
            "recent_decisions_degraded_tiers": frozenset(),
            "recent_decisions_contradictions": [],
        }
    )
    assert section == ""


def test_total_failure_renders_nothing():
    """All three tiers degraded, zero decisions → empty (treat as cold start)."""
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [],
            "recent_decisions_degraded_tiers": frozenset({"capability", "discipline", "recency"}),
            "recent_decisions_contradictions": [],
        }
    )
    assert section == ""


# -----------------------------------------------------------------------------
# Section rendering
# -----------------------------------------------------------------------------


def test_capability_tier_renders_with_capability_header():
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [_td("decision:a", "capability", title="rotate auth")],
            "recent_decisions_degraded_tiers": frozenset(),
            "recent_decisions_contradictions": [],
        }
    )
    assert "Decisions previously made about this capability:" in section
    assert "rotate auth" in section


def test_three_tier_headers_in_order():
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [
                _td("decision:c", "capability"),
                _td("decision:d", "discipline"),
                _td("decision:r", "recency"),
            ],
            "recent_decisions_degraded_tiers": frozenset(),
            "recent_decisions_contradictions": [],
        }
    )
    cap_idx = section.index("Decisions previously made about this capability:")
    disc_idx = section.index("Recent thinking in this discipline:")
    rec_idx = section.index("Other recent decisions on this product:")
    assert cap_idx < disc_idx < rec_idx


def test_anti_anchor_instruction_always_rendered_when_non_empty():
    """Spec §6.3 — anti-anchor line always present when any tier section renders."""
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [_td("decision:a", "capability")],
            "recent_decisions_degraded_tiers": frozenset(),
            "recent_decisions_contradictions": [],
        }
    )
    assert "Prior decisions are context, not commands" in section
    assert "Revise, reverse, or override" in section


# -----------------------------------------------------------------------------
# Degradation footnote
# -----------------------------------------------------------------------------


def test_partial_degradation_renders_footnote():
    """One tier failed but others surfaced → footnote names the failed tier."""
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [_td("decision:a", "discipline")],
            "recent_decisions_degraded_tiers": frozenset({"capability"}),
            "recent_decisions_contradictions": [],
        }
    )
    assert "[Layer 5 partial: capability unavailable this turn" in section


def test_no_footnote_when_all_tiers_healthy():
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [_td("decision:a", "capability")],
            "recent_decisions_degraded_tiers": frozenset(),
            "recent_decisions_contradictions": [],
        }
    )
    assert "Layer 5 partial" not in section


# -----------------------------------------------------------------------------
# Contradiction notices (TODO-17)
# -----------------------------------------------------------------------------


def test_contradiction_notice_rendered():
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [
                _td("decision:a", "capability", outcome="accepted", caps=["auth"]),
                _td("decision:b", "capability", outcome="rejected", caps=["auth"]),
            ],
            "recent_decisions_degraded_tiers": frozenset(),
            "recent_decisions_contradictions": [("decision:a", "decision:b", "auth")],
        }
    )
    assert "[Layer 5: decisions decision:a and decision:b conflict on capability auth" in section


# -----------------------------------------------------------------------------
# Outcome downweighting (spec §6.3, reconciled with actual schema:
# outcome ∈ {accepted, rejected, superseded, pending})
# -----------------------------------------------------------------------------


def test_outcome_rejected_marks_decision_with_tag():
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [
                _td("decision:a", "capability", title="we considered X", outcome="rejected"),
            ],
            "recent_decisions_degraded_tiers": frozenset(),
            "recent_decisions_contradictions": [],
        }
    )
    assert "[rejected]" in section
    assert "we considered X" in section


def test_weighted_score_outcome_multipliers():
    """Outcome weights flow into _weighted_score:
    accepted=1.0, pending=0.5, rejected=0.3, superseded=0.0."""
    sc = ShellComposer()
    ok = _td("decision:s", "capability", outcome="accepted", relevance_score=0.9)
    pending = _td("decision:p", "capability", outcome="pending", relevance_score=0.9)
    rejected = _td("decision:r", "capability", outcome="rejected", relevance_score=0.9)
    assert sc._weighted_score(ok) == 0.9 * 1.0
    assert abs(sc._weighted_score(pending) - 0.9 * 0.5) < 1e-9
    assert abs(sc._weighted_score(rejected) - 0.9 * 0.3) < 1e-9


# -----------------------------------------------------------------------------
# _format_decision_line — title/rationale redundancy detection
# -----------------------------------------------------------------------------


def test_format_drops_title_when_rationale_starts_with_it():
    """Synthesizer-written decisions often have title = truncated prefix of
    rationale. Dropping the title prefix avoids ~80 wasted prompt tokens per
    row and a mid-word visual cut."""
    decision = _td(
        "decision:x",
        "capability",
        title="Architectural mapping and decision trees should be treated as maturity-stage",
        rationale="Architectural mapping and decision trees should be treated as maturity-stage deliverables that become essential when capabilities reach 'stood up'.",
    )
    line = ShellComposer._format_decision_line(decision)
    # Should NOT contain the duplicate-prefix render
    assert line.count("Architectural mapping") == 1
    # Should contain the full rationale content (truncated to 200)
    assert "maturity-stage deliverables" in line


def test_format_keeps_title_when_meaningfully_different():
    """When title is NOT a prefix of rationale, render both — the title
    carries distinct framing."""
    decision = _td(
        "decision:y",
        "capability",
        title="Auth Rotation Policy",
        rationale="We adopted 90-day rotation cadence after the 2024 token-leak incident; manual override requires gate approval.",
    )
    line = ShellComposer._format_decision_line(decision)
    assert "Auth Rotation Policy" in line
    assert "90-day rotation" in line


def test_format_outcome_tag_only_when_not_accepted():
    """Accepted is the default — no tag rendered. Rejected/pending/superseded
    each get a [tag] in the line."""
    line_accepted = ShellComposer._format_decision_line(
        _td("decision:a", "capability", title="x", rationale="x rationale", outcome="accepted")
    )
    line_rejected = ShellComposer._format_decision_line(
        _td("decision:b", "capability", title="y", rationale="y rationale", outcome="rejected")
    )
    assert "[accepted]" not in line_accepted
    assert "[rejected]" in line_rejected


def test_format_handles_empty_title_or_rationale():
    """Defensive: missing-field cases shouldn't blow up."""
    decision_no_rationale = _td("decision:t", "capability", title="just a title", rationale="")
    line = ShellComposer._format_decision_line(decision_no_rationale)
    assert "just a title" in line

    decision_no_title = _td("decision:r", "capability", title="", rationale="just a rationale")
    line = ShellComposer._format_decision_line(decision_no_title)
    assert "just a rationale" in line


def test_within_tier_sort_rejected_sinks_below_accepted():
    """Within a tier, rejected decisions sort below accepted ones (outcome
    multiplier brings rejected score from 0.9 down to 0.27 vs 0.9)."""
    sc = ShellComposer()
    section = sc._build_layer5_section(
        {
            "recent_decisions": [
                _td("decision:r", "capability", title="rejected-one", outcome="rejected"),
                _td("decision:a", "capability", title="accepted-one", outcome="accepted"),
            ],
            "recent_decisions_degraded_tiers": frozenset(),
            "recent_decisions_contradictions": [],
        }
    )
    assert section.index("accepted-one") < section.index("rejected-one")
