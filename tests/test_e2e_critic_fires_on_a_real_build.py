"""The critic must actually RUN on a real arm build — not just in unit tests with a fake LLM.

Every other e2e build test opts OUT of adversarial review (no_adversarial_review), and for a good
reason: letting a live model adjudicate `assert built is True` makes CI non-deterministic. But
opting out everywhere leaves a hole exactly where it matters — nothing would prove the critic fires
end-to-end, through dispatch, on output a real arm actually produced. An unfired gate is a vacuous
gate, and this repo has shipped those before.

So this test asserts the WIRING, not the verdict: the critic ran, it saw the real diff, and it
returned a judgement. WHAT it judged is the model's business and is not allowed to fail CI.
"""

from __future__ import annotations

import subprocess

import pytest

from core.engine.solution import Solution


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_the_critic_runs_on_a_real_build_and_sees_the_real_diff(tmp_path, monkeypatch):
    import core.engine.arms.critic as critic_mod
    import core.engine.arms.dispatch as dispatch
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "arm_adversarial_review", True)
    monkeypatch.setattr(settings, "arm_repair_budget", 0)  # no repair — we are testing the gate, not recovery

    repo = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-q", repo], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
    (tmp_path / "repo" / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", repo, "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "seed"], check=True)

    orig = Workspace.create.__func__
    monkeypatch.setattr(
        Workspace, "create", classmethod(lambda cls, label="arm", repo_root=None: orig(cls, label, repo))
    )

    seen: dict = {}
    real_verify = critic_mod.adversarial_verify

    async def _spy(solution, plan, result, llm=None):
        verdict = await real_verify(solution, plan, result, llm=llm)
        seen["ran"] = True
        seen["diff"] = result.workspace.diff() if result.workspace else ""
        seen["verdict"] = verdict
        return verdict

    monkeypatch.setattr(critic_mod, "adversarial_verify", _spy)

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(dispatch, "capture_outcome", _noop)

    out = await dispatch.dispatch_solution(Solution(intent="scaffold a file", domain_hint="scaffold"))
    assert out is not None
    _domain, result, verdict = out

    assert seen.get("ran") is True, "the critic must fire on a real build — an unfired gate is a vacuous gate"
    assert "scaffold.txt" in seen["diff"], (
        "the critic must receive the ACTUAL diff, including newly CREATED files. Plain `git diff` "
        "hides untracked files, which fed the critic a blank page for every new-file build."
    )
    # The verdict itself is the model's call. We assert only that it MADE one — a real, coherent
    # judgement — and never that it said yes. An LLM must not be able to fail this suite.
    assert seen["verdict"].source == "critic"
    assert isinstance(seen["verdict"].passed, bool)
    assert seen["verdict"].reason, "a critic verdict must always carry its reasoning"

    # And a refutation must NOT be mistaken for a broken environment: it is a judged, repairable
    # failure. Only an unavailable critic parks.
    if not verdict.passed:
        assert verdict.parked is False, "a refuted build was JUDGED — it is not parked"

    if result.workspace is not None:
        result.workspace.discard()
