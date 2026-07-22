"""Process-local, provider-aware admission control for LLM calls.

The scheduler is deliberately transport-agnostic: it does not own credentials,
choose providers, retry requests, or imply provider-side reserved capacity. It
only prevents independent ACE tasks from creating unbounded local contention on
the same access class and records how long a call waited for admission.
"""

from __future__ import annotations

import asyncio
import time
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass

from core.engine.core.access import AccessClass, access_profile_for
from core.engine.core.config import settings


@dataclass(frozen=True)
class ProviderLease:
    route: str
    concurrency_limit: int
    queue_ms: int
    active_at_admission: int


@dataclass
class _RouteState:
    semaphore: asyncio.Semaphore
    limit: int
    active: int = 0
    waiting: int = 0


_loop_states: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, _RouteState]] = weakref.WeakKeyDictionary()


def _route(provider: object) -> tuple[str, int]:
    name = type(provider).__name__
    profile = access_profile_for(provider)
    if name in {"CLIProvider", "CodexCLIProvider"}:
        return f"subprocess:{name}", settings.llm_subprocess_concurrency
    if profile.access_class == AccessClass.SUBSCRIPTION:
        return f"subscription:{profile.billing_source}", settings.llm_subscription_concurrency
    if profile.access_class == AccessClass.METERED_API:
        return f"metered:{profile.billing_source}", settings.llm_metered_concurrency
    if profile.access_class == AccessClass.LOCAL:
        return f"local:{profile.billing_source}", settings.llm_local_concurrency
    return f"unclassified:{name}", 1


def _state_for(provider: object) -> tuple[str, _RouteState]:
    loop = asyncio.get_running_loop()
    route, limit = _route(provider)
    states = _loop_states.setdefault(loop, {})
    state = states.get(route)
    # Settings can be patched in tests or reloaded between app lifecycles.
    if state is None or state.limit != limit:
        state = _RouteState(asyncio.Semaphore(limit), limit)
        states[route] = state
    return route, state


@asynccontextmanager
async def provider_slot(provider: object):
    """Admit one call and yield secret-free queue/concurrency measurements."""
    route, state = _state_for(provider)
    queued_at = time.monotonic()
    state.waiting += 1
    try:
        await state.semaphore.acquire()
    finally:
        state.waiting -= 1
    state.active += 1
    lease = ProviderLease(
        route=route,
        concurrency_limit=state.limit,
        queue_ms=max(0, int((time.monotonic() - queued_at) * 1000)),
        active_at_admission=state.active,
    )
    try:
        yield lease
    finally:
        state.active -= 1
        state.semaphore.release()


def reset_scheduler_for_tests() -> None:
    """Clear loop-scoped state. Intended only for deterministic unit tests."""
    _loop_states.clear()
