"""Stop for the right reasons — including BEFORE you start.

The session stops well once it is running: parked on a dead environment, halted on a systemic run
of failures, honest about an unapproved backlog. But it will happily BEGIN an eight-hour unattended
run on an engine that cannot survive one, and discover that at 3am with a wedged process and
nothing to show.

The live evidence: get_llm() resolves to CLIProvider (a `claude` subprocess per call). It works in
short bursts — measured at 4s — and WEDGES under sustained load: the e2e suite hung at 36 minutes
and 0.3% CPU with no subprocess even running. A single CodeArm build makes four LLM calls in
planning alone. An overnight session on that provider produces a hang, not builds.

So: check the engine before the drive. A preflight that costs seconds and fails with a diagnosis is
worth more than an eight-hour hang that fails with silence.

The discipline that keeps it from becoming its own liability: a preflight may only REFUSE for
things it has actually established. It is not allowed to be superstitious — an unknown provider is
not a broken one, and a preflight that blocks work it cannot justify blocking is worse than none.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_an_unreachable_model_is_caught_in_seconds_not_at_3am(monkeypatch):
    """The whole point: fail before the run, not eight hours into it."""
    import core.engine.arms.preflight as pf
    from core.engine.core.exceptions import LLMError

    class _Dead:
        async def complete(self, *a, **kw):
            raise LLMError("model unreachable")

    monkeypatch.setattr(pf, "get_llm", lambda: _Dead())

    report = await pf.preflight(sustained=True)

    assert report.ok is False
    assert "unreachable" in report.diagnosis.lower() or "model" in report.diagnosis.lower()


@pytest.mark.asyncio
async def test_the_subprocess_provider_is_WARNED_about_but_never_BLOCKED(monkeypatch):
    """I originally REFUSED to start on CLIProvider, on the theory that it "wedges under sustained
    load". That theory was never tested and it was wrong.

    What actually happens, measured by counting every model call in a real build: ~20 calls, each
    degrading from 10.8s to 91.6s — 15-25 minutes for one build. It is SLOW, not broken. The build
    that looked like a 24-minute hang was a build working, exactly on schedule.

    A preflight may only refuse for what it has ESTABLISHED. Blocking real work on an untested
    theory is the worst thing a gate can do: it looks principled and it is just wrong. So the CLI is
    reported honestly — expect a slow build — and the runaway guard is the BUILD BUDGET, which parks
    with a diagnosis instead of banning the provider outright."""
    import core.engine.arms.preflight as pf

    class _CLIProvider:
        async def complete(self, *a, **kw):
            return "OK"

    monkeypatch.setattr(pf, "get_llm", lambda: _CLIProvider())

    report = await pf.preflight(sustained=True)

    assert report.ok is True, "the CLI is SLOW, not broken — never block real work on an untested theory"
    assert report.warning, "but say so: a build will take 15-25 minutes on this provider"
    assert "slow" in report.warning.lower() or "minutes" in report.warning.lower()
    assert "CLAUDE_CODE_OAUTH_TOKEN" in report.warning, "and offer the faster path"


@pytest.mark.asyncio
async def test_the_same_provider_is_fine_for_a_SINGLE_CALL(monkeypatch):
    """It must not be superstitious — but the line is drawn where the EVIDENCE puts it.

    My first version allowed a one-BUILD session on the CLI, reasoning that one build is a "short
    burst". A real max_builds=1 run then wedged for 24 minutes at 0% CPU and produced nothing. One
    CodeArm build is four-plus model calls before it writes a line. A burst is a single CALL, not a
    single build — so sustained=False now means exactly that, and every build session passes True."""
    import core.engine.arms.preflight as pf

    class _CLIProvider:
        async def complete(self, *a, **kw):
            return "OK"

    monkeypatch.setattr(pf, "get_llm", lambda: _CLIProvider())

    report = await pf.preflight(sustained=False)

    assert report.ok is True, "a single CALL on the CLI is fine (~4s, measured) — do not cry wolf"


@pytest.mark.asyncio
async def test_a_healthy_api_provider_passes_for_a_long_run(monkeypatch):
    import core.engine.arms.preflight as pf

    class _ClaudeProvider:
        async def complete(self, *a, **kw):
            return "OK"

    monkeypatch.setattr(pf, "get_llm", lambda: _ClaudeProvider())

    report = await pf.preflight(sustained=True)

    assert report.ok is True
    assert report.provider == "_ClaudeProvider"


@pytest.mark.asyncio
async def test_an_unknown_provider_is_not_assumed_broken(monkeypatch):
    """A preflight may only refuse for what it has ESTABLISHED. An unfamiliar provider that answers
    a probe is a working provider."""
    import core.engine.arms.preflight as pf

    class _SomeFutureProvider:
        async def complete(self, *a, **kw):
            return "OK"

    monkeypatch.setattr(pf, "get_llm", lambda: _SomeFutureProvider())

    report = await pf.preflight(sustained=True)
    assert report.ok is True, "unknown is not broken — do not be superstitious"


@pytest.mark.asyncio
async def test_the_probe_cannot_hang_the_preflight(monkeypatch):
    """A preflight that hangs is the very disease it exists to prevent."""
    import asyncio

    import core.engine.arms.preflight as pf

    class _Hangs:
        async def complete(self, *a, **kw):
            await asyncio.sleep(3600)

    monkeypatch.setattr(pf, "get_llm", lambda: _Hangs())

    report = await asyncio.wait_for(pf.preflight(sustained=True, probe_timeout=0.2), timeout=10)

    assert report.ok is False
    assert "did not answer" in report.diagnosis.lower() or "timed out" in report.diagnosis.lower()


@pytest.mark.asyncio
async def test_the_session_refuses_to_start_when_preflight_fails(monkeypatch):
    """Reachability: an unrun preflight is a decorative module."""
    import core.engine.arms.preflight as pf
    import core.engine.arms.session as session

    built = []

    async def _fail(sustained=False, probe_timeout=30.0):
        return pf.Preflight(ok=False, provider="X", diagnosis="the engine is on fire")

    async def _build(*a, **kw):
        built.append(1)
        return {"built": True}

    monkeypatch.setattr(session, "preflight", _fail)
    monkeypatch.setattr(session, "build_spec", _build)

    out = await session.run_build_session(product_id="product:platform", max_builds=5)

    assert built == [], "the session must not burn a single build on a broken engine"
    assert out["stopped_because"] == "preflight failed"
    assert out["needs_human"] is True
    assert "on fire" in out["diagnosis"]


@pytest.mark.asyncio
async def test_a_passing_preflight_does_not_get_in_the_way(monkeypatch):
    import core.engine.arms.preflight as pf
    import core.engine.arms.session as session

    async def _pass(sustained=False, probe_timeout=30.0):
        return pf.Preflight(ok=True, provider="ClaudeProvider", diagnosis="")

    async def _no_work(product_id, pool=None, exclude=None):
        return None

    async def _zero(*a, **kw):
        return 0

    monkeypatch.setattr(session, "preflight", _pass)
    monkeypatch.setattr(session, "_next_buildable_spec", _no_work)
    monkeypatch.setattr(session, "_count_unapproved_specs", _zero)
    monkeypatch.setattr(session, "reconcile_stale_runs", _zero)
    monkeypatch.setattr(session, "reconcile_stranded_specs", _zero)

    out = await session.run_build_session(product_id="product:platform")
    assert out["stopped_because"] == "no work left"
