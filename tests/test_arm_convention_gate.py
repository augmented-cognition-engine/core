"""The fail-closed verify-check gate, wired into BrainHandArm.verify() through the
extension registry seam (`core/engine/extensions/registry.py`).

verify() no longer imports a hardcoded convention checker — it loops over every check
registered via `Registry().register_verify_check(fn)` and runs it against the plan's
generated files. This test drives the seam with a FAKE check (no ACE-specific rules)
to prove the wiring itself, independent of whatever real checks an extension registers:

ENFORCED violations must block the pass — even when tests are green and the adversarial
critic is satisfied — and must reach the repair loop's regeneration context so the arm
gets a chance to fix it. ADVISORY violations must NOT block the pass; they only need to
surface in the Verdict's reason so a human sees them. With NO check registered, the seam
is a no-op and a clean plan passes exactly as it did before the gate existed.

Harness lifted from tests/test_repair_keeps_the_depth.py and tests/test_failed_tests_say_why.py:
a concrete BrainHandArm subclass with a stubbed `generate` phase (captures the repair ctx) and
`_critic`, with ExecutionRuntime.run_tests / .run monkeypatched so no real subprocess or LLM runs.
"""

from __future__ import annotations

import pytest

import core.engine.extensions.registry as registry
from core.engine.arms.base import Action, ActionPlan, ArmResult, RiskTier


class _WS:
    path = "/tmp/x"


def _arm():
    from core.engine.arms.brain_hand_arm import BrainHandArm

    class _Concrete(BrainHandArm):
        domain = "code"

        def can_handle(self, s):
            return True

    arm = _Concrete()
    arm._intent = "add the widget"
    arm.regen_calls = []
    return arm


def _plan(content: str) -> ActionPlan:
    return ActionPlan(
        summary="code: add the widget",
        actions=[Action(verb="write_file", args={"path": "x.py", "content": content}, risk=RiskTier.REVERSIBLE)],
        test_cmd=["pytest"],
        surfaced_concerns=[],
    )


def _fake_check(marker: str, severity: str):
    """A minimal registrable verify check: flags any file whose content contains `marker`."""

    def check(files):
        out = []
        for f in files:
            if marker in (f.get("content") or ""):
                out.append(
                    {"rule": "fake", "severity": severity, "file": f.get("path", ""), "line": 1, "snippet": marker}
                )
        return out

    return check


@pytest.mark.asyncio
async def test_enforced_violation_blocks_and_reaches_repair(monkeypatch):
    """A fake enforced violation must NOT pass on the first attempt, even with tests green
    and the critic fully satisfied — and the regeneration the inner repair loop calls must
    be told exactly what to fix."""
    monkeypatch.setattr(registry, "_verify_checks", [])
    registry.Registry().register_verify_check(_fake_check("BADMARKER", "enforced"))

    arm = _arm()

    async def _critic(concerns, ws):
        return True, []  # the no-slop gate is fully satisfied — the fake check is the ONLY problem

    async def _run_tests(self, cmd, ws):
        return True, ""  # tests are green throughout

    async def _run(self, plan, ws):
        return None

    async def _generate(solution, profile, ctx):
        arm.regen_calls.append(ctx)
        # the repair fixes the violation — proves the loop can recover once checks are clean
        return {"files": [{"path": "x.py", "content": "clean content"}], "test_cmd": ["pytest"]}

    arm._critic = _critic
    arm.phase["generate"] = _generate
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run_tests", _run_tests)
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run", _run)

    plan = _plan("BADMARKER")
    verdict = await arm.verify(ArmResult(plan=plan, workspace=_WS()), plan)

    assert arm.regen_calls, (
        "verify() must NOT have passed on the first attempt — the enforced violation should have "
        "driven it into the repair branch, which is the only way `generate` gets called here"
    )
    repair_ctx = arm.regen_calls[0]
    assert "fake" in repair_ctx["repair"], "the repair hint must name the violated rule"
    assert "x.py" in repair_ctx["repair"], "and the file it was found in"

    # once the regenerated file is clean, the gate lets the (now-fixed) build through
    assert verdict.passed is True, "a build that fixes its enforced violation must be able to pass"


@pytest.mark.asyncio
async def test_empty_regen_does_not_silently_pass_the_original_violation(monkeypatch):
    """If a check-triggered repair pass's `generate` returns no files, verify() must NOT fall
    through to a clean pass on the next iteration. Without a guard, the next pass would scan
    the (now-empty) regenerated plan, find zero violations, and return passed=True — while the
    ORIGINAL, untouched, still-violating file is what actually ships. `repair()` already guards
    this exact case (`if not files: return None`); this proves the inner loop in verify() does too."""
    monkeypatch.setattr(registry, "_verify_checks", [])
    registry.Registry().register_verify_check(_fake_check("BADMARKER", "enforced"))

    arm = _arm()

    async def _critic(concerns, ws):
        return True, []  # the no-slop gate is fully satisfied — the fake check is the only problem

    async def _run_tests(self, cmd, ws):
        return True, ""  # tests are green throughout

    async def _run(self, plan, ws):
        return None

    async def _generate(solution, profile, ctx):
        arm.regen_calls.append(ctx)
        return {"files": []}  # nothing regenerated — must NOT be treated as a clean pass

    arm._critic = _critic
    arm.phase["generate"] = _generate
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run_tests", _run_tests)
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run", _run)

    plan = _plan("BADMARKER")
    verdict = await arm.verify(ArmResult(plan=plan, workspace=_WS()), plan)

    assert arm.regen_calls, "the enforced violation should have driven verify() into the repair branch"
    assert verdict.passed is False, "an empty regeneration must not silently pass the untouched violation"
    assert "fake" in verdict.reason, "the reason must name the unresolved enforced violation"


@pytest.mark.asyncio
async def test_advisory_violation_passes_and_surfaces_in_reason(monkeypatch):
    """A fake advisory violation must NOT block the pass — only surface for a human."""
    monkeypatch.setattr(registry, "_verify_checks", [])
    registry.Registry().register_verify_check(_fake_check("BADMARKER", "advisory"))

    arm = _arm()

    async def _critic(concerns, ws):
        return True, []

    async def _run_tests(self, cmd, ws):
        return True, ""

    async def _generate(solution, profile, ctx):  # must never be called — nothing to repair
        arm.regen_calls.append(ctx)
        return {"files": [], "test_cmd": ["pytest"]}

    arm._critic = _critic
    arm.phase["generate"] = _generate
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run_tests", _run_tests)

    plan = _plan("BADMARKER")
    verdict = await arm.verify(ArmResult(plan=plan, workspace=_WS()), plan)

    assert verdict.passed is True, "advisory-only violations must not block the build"
    assert "fake" in verdict.reason, "the advisory violation must surface for a human"
    assert not arm.regen_calls, "advisory-only should pass on the first attempt — no repair needed"


@pytest.mark.asyncio
async def test_malformed_violation_is_skipped_not_fatal(monkeypatch):
    """Any extension can register a check now — the seam must survive one that RETURNS
    (doesn't raise) a malformed violation: missing a required key, a bad severity, or not
    even a dict. The `try/except` around `check(files)` only guards the CALL; a malformed
    dict crossing `v["severity"]` etc. downstream must not KeyError out of verify() and
    crash the build. The well-formed enforced violation from the SAME check must still be
    read and still block."""
    monkeypatch.setattr(registry, "_verify_checks", [])

    def _bad_check(files):
        out = [
            {"rule": "no-severity-key", "file": "x.py", "line": 2},  # malformed: missing severity
            None,  # malformed: not even a dict
        ]
        for f in files:
            if "BADMARKER" in (f.get("content") or ""):
                out.append({"rule": "fake", "severity": "enforced", "file": "x.py", "line": 1})  # well-formed
        return out

    registry.Registry().register_verify_check(_bad_check)

    arm = _arm()

    async def _critic(concerns, ws):
        return True, []

    async def _run_tests(self, cmd, ws):
        return True, ""

    async def _run(self, plan, ws):
        return None

    async def _generate(solution, profile, ctx):
        arm.regen_calls.append(ctx)
        return {"files": [{"path": "x.py", "content": "clean content"}], "test_cmd": ["pytest"]}

    arm._critic = _critic
    arm.phase["generate"] = _generate
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run_tests", _run_tests)
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run", _run)

    plan = _plan("BADMARKER")
    verdict = await arm.verify(ArmResult(plan=plan, workspace=_WS()), plan)  # must not raise

    assert arm.regen_calls, "the well-formed enforced violation must still have driven repair"
    repair_ctx = arm.regen_calls[0]
    assert "fake" in repair_ctx["repair"], "the well-formed violation must still reach the repair hint"
    assert verdict.passed is True, "once the well-formed violation is fixed, the malformed ones must not block"


@pytest.mark.asyncio
async def test_no_check_registered_passes_unchanged(monkeypatch):
    """Empty seam — no verify check registered at all: verify() must behave exactly as before
    this gate landed, for content that would have tripped a real check had one been registered."""
    monkeypatch.setattr(registry, "_verify_checks", [])

    arm = _arm()

    async def _critic(concerns, ws):
        return True, []

    async def _run_tests(self, cmd, ws):
        return True, ""

    async def _generate(solution, profile, ctx):  # must never be called
        arm.regen_calls.append(ctx)
        return {"files": [], "test_cmd": ["pytest"]}

    arm._critic = _critic
    arm.phase["generate"] = _generate
    monkeypatch.setattr("core.engine.arms.execution.runtime.ExecutionRuntime.run_tests", _run_tests)

    plan = _plan("BADMARKER")
    verdict = await arm.verify(ArmResult(plan=plan, workspace=_WS()), plan)

    assert verdict.passed is True
    assert not arm.regen_calls, "with no check registered, nothing can block the first attempt"
