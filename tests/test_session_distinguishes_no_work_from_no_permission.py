"""'Nothing to do' and 'nothing you've let me do' are different facts.

Found in production: 16 draft specs, 0 approved. So a build session reports

    stopped_because: "no work left"

...which reads as a clean sweep — everything's done, go home. The truth was that sixteen specs were
sitting in draft awaiting a human's approval, and nothing anywhere said so. `ace_pending_gates`
reported 0. The loop would have quietly done nothing, successfully, forever.

This is the parked-vs-failed mistake in a new place: two very different states collapsed into one
cheerful message. An empty build queue because the work is DONE and an empty build queue because
nobody has APPROVED anything demand opposite responses from a human, and the session must say which
one it is.

Note what is deliberately NOT fixed here: the session does not approve specs for itself. The
approval gate is the human's authority over what gets built, and a loop that promotes its own work
into its own queue has quietly removed the person it is supposed to be partnering with. It reports;
it does not self-authorise.
"""

from __future__ import annotations

import pytest


async def _noop(*a, **kw):
    return 0


@pytest.mark.asyncio
async def test_an_empty_queue_with_drafts_waiting_is_reported_as_needing_the_human(monkeypatch):
    import core.engine.arms.session as session

    async def _no_approved(product_id, pool=None, exclude=None):
        return None  # nothing APPROVED

    async def _drafts(product_id, pool=None):
        return 16  # ...but sixteen drafts are waiting on a person

    monkeypatch.setattr(session, "_next_buildable_spec", _no_approved)
    monkeypatch.setattr(session, "_count_unapproved_specs", _drafts)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop)
    monkeypatch.setattr(session, "reconcile_stranded_specs", _noop)

    out = await session.run_build_session(product_id="product:platform")

    assert out["stopped_because"] == "nothing approved", (
        "an empty queue with drafts waiting is NOT 'no work left' — that reads as a clean sweep, and "
        "the loop would sit idle forever while the backlog waits on a signature nobody asked for"
    )
    assert out["needs_human"] is True
    assert out["awaiting_approval"] == 16
    assert "16" in out["diagnosis"] and "approv" in out["diagnosis"].lower()


@pytest.mark.asyncio
async def test_a_genuinely_empty_backlog_is_still_a_clean_sweep(monkeypatch):
    """The guard must not cry wolf: with nothing approved AND nothing drafted, there is genuinely no
    work, and that is a success — not something to wake a human for."""
    import core.engine.arms.session as session

    async def _no_approved(product_id, pool=None, exclude=None):
        return None

    async def _no_drafts(product_id, pool=None):
        return 0

    monkeypatch.setattr(session, "_next_buildable_spec", _no_approved)
    monkeypatch.setattr(session, "_count_unapproved_specs", _no_drafts)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop)
    monkeypatch.setattr(session, "reconcile_stranded_specs", _noop)

    out = await session.run_build_session(product_id="product:platform")

    assert out["stopped_because"] == "no work left"
    assert out["needs_human"] is False, "nothing to do is a success, not an alarm"


@pytest.mark.asyncio
async def test_the_queue_running_dry_MID_SESSION_is_not_an_alarm_either(monkeypatch):
    """If we built everything that was approved, that is a good day's work — even if drafts remain."""
    import core.engine.arms.session as session

    built: list[str] = []

    async def _one_then_none(product_id, pool=None, exclude=None):
        return "agent_spec:a" if not built else None

    async def _build(spec_id, product_id="product:platform", pool=None):
        built.append(spec_id)
        return {"built": True, "branch": "arm/a"}

    async def _drafts(product_id, pool=None):
        return 16

    monkeypatch.setattr(session, "_next_buildable_spec", _one_then_none)
    monkeypatch.setattr(session, "build_spec", _build)
    monkeypatch.setattr(session, "_count_unapproved_specs", _drafts)
    monkeypatch.setattr(session, "reconcile_stale_runs", _noop)
    monkeypatch.setattr(session, "reconcile_stranded_specs", _noop)

    out = await session.run_build_session(product_id="product:platform", max_builds=5)

    assert len(out["built"]) == 1
    assert out["stopped_because"] == "no work left", "we drained the approved queue — that is success"
    assert out["needs_human"] is False, "drafts remaining is not an emergency when we DID build"
    assert out["awaiting_approval"] == 16, "but still TELL them the drafts are there"


@pytest.mark.asyncio
async def test_counting_drafts_is_fail_safe(monkeypatch):
    """A broken count must never turn a working session into an error."""
    import core.engine.arms.session as session

    class _Dead:
        def connection(self):
            raise RuntimeError("db gone")

    assert await session._count_unapproved_specs("product:platform", pool=_Dead()) == 0
