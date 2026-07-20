"""Does the router actually route, against a real model?

Every other router test injects a fake LLM — which proves the plumbing and nothing about whether a
real model can tell a code task from a design task. That distinction is the entire point, and it
was measured wrong before: against the real 17-spec backlog, keyword routing produced

    NO ARM 9  ·  design 6  ·  code 1  ·  ship 1

53% unroutable, and "Implement comprehensive rate limiting across all API endpoints" classed as
DESIGN while "Cascade calibration / CascadeRouter prod instantiation" went to the SHIP GATE because
it contains the word "prod".

These cases are taken verbatim from that backlog. They assert only what a competent router must get
right — not fine judgement calls, which would make CI hostage to a model's mood.
"""

from __future__ import annotations

import pytest

from core.engine.solution import Solution


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.parametrize(
    "intent,expected",
    [
        # The two verbatim production misroutes.
        ("Implement comprehensive rate limiting across all API endpoints to prevent abuse", "code"),
        ("Cascade calibration / CascadeRouter prod instantiation", "code"),
        # A real schema change must find the data arm.
        ("Bi-temporal edges (valid_at/invalid_at, invalidate-not-delete)", "data"),
        # And a genuine surface must still find design — the fix must not simply route everything to code.
        ("Canvas maturity + conceptual onboarding (partnership surface)", "design"),
    ],
)
async def test_the_real_classifier_routes_real_backlog_items(intent, expected):
    from core.engine.arms.router import choose_arm

    arm = await choose_arm(Solution(intent=intent))

    assert arm is not None, f"{intent!r} routed NOWHERE — 53% of the backlog used to land here"
    assert arm.domain == expected, f"{intent!r} → {arm.domain}, expected {expected}"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_a_gate_is_never_handed_a_build_by_the_real_classifier():
    """The misroute that cost a whole live session: a gate emits no files, so the build comes out
    empty and the gate then refuses its own emptiness as vacuous. A guaranteed dead end."""
    from core.engine.arms.router import choose_arm

    arm = await choose_arm(
        Solution(intent="Harden the production deployment pipeline with retries and rollback"),
        producer_only=True,
    )
    assert arm is None or arm.is_gate is False, "a gate must never be selected to BUILD"
