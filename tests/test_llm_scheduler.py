import asyncio

import pytest

from core.engine.core.llm import CodexAppServerProvider
from core.engine.core.llm_scheduler import provider_slot, reset_scheduler_for_tests


@pytest.mark.asyncio
async def test_subscription_scheduler_caps_concurrency_and_reports_queue(monkeypatch):
    from core.engine.core import llm_scheduler

    reset_scheduler_for_tests()
    monkeypatch.setattr(llm_scheduler.settings, "llm_subscription_concurrency", 1)
    provider = CodexAppServerProvider()
    entered = asyncio.Event()
    release = asyncio.Event()
    leases = []
    active = 0
    peak = 0

    async def work(first: bool = False):
        nonlocal active, peak
        async with provider_slot(provider) as lease:
            leases.append(lease)
            active += 1
            peak = max(peak, active)
            if first:
                entered.set()
                await release.wait()
            active -= 1

    first = asyncio.create_task(work(first=True))
    await entered.wait()
    second = asyncio.create_task(work())
    await asyncio.sleep(0.02)
    assert not second.done()
    release.set()
    await asyncio.gather(first, second)

    assert peak == 1
    assert leases[0].concurrency_limit == 1
    assert leases[1].queue_ms >= 10


@pytest.mark.asyncio
async def test_exec_transport_has_separate_subprocess_budget(monkeypatch):
    from core.engine.core import llm_scheduler
    from core.engine.core.llm import CodexCLIProvider

    reset_scheduler_for_tests()
    monkeypatch.setattr(llm_scheduler.settings, "llm_subprocess_concurrency", 1)
    async with provider_slot(CodexCLIProvider()) as lease:
        assert lease.route == "subprocess:CodexCLIProvider"
        assert lease.concurrency_limit == 1
