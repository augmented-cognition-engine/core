"""A pooled connection must never be handed to a different event loop.

THE BUG
-------
SurrealDB's async WebSocket connection binds to the event loop that created it — its
pending futures live on that loop. Hand it to a task on another loop and you get

    RuntimeError: Task ... got Future <Future pending> attached to a different loop

The pool health-checked connections on RELEASE:

    async def release(conn):
        try:
            await conn.query("RETURN true")   # runs on the loop we are LEAVING
            await self._pool.put(conn)
        except Exception:
            ... recycle ...

which is the one place the check can never fail for this defect. The connection is fine
on its own loop; that is the entire point. So it passed, went back into the pool still
bound to a loop that was about to be closed, and the NEXT acquirer — on a new loop — blew
up on first use, inside the caller, with a message about futures that names nothing the
caller did.

There was no check on ACQUIRE, which is the only place it could have been caught.

WHERE IT BIT
------------
Under pytest, where pytest-asyncio gives each test a fresh loop: a connection created in
one test was reused in another, and the failure was written off as a load flake because it
only appeared in a full run. It never had anything to do with load.

It is not test-only. Anything that calls `asyncio.run()` on a worker thread and touches
the GLOBAL pool creates the same cross-loop hand-off — which is exactly why callers in
that position had learned to construct a private `SurrealPool(max_connections=1)` instead.
That workaround is a symptom of this bug, not a design.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from core.engine.core.db import SurrealPool

pytestmark = pytest.mark.e2e


async def _use(pool: SurrealPool) -> int:
    async with pool.connection() as db:
        await db.query("RETURN 1")
    return 1


def test_a_connection_is_never_reused_across_event_loops() -> None:
    """THE regression, reproduced deterministically.

    Run against the pool on one loop, let that loop close, then run again on a fresh loop
    — exactly what pytest does between two tests. The second run must not receive the
    first run's connection.
    """
    pool = SurrealPool(max_connections=2)

    asyncio.run(_use(pool))  # loop 1 — fills the pool with loop-1 connections
    asyncio.run(_use(pool))  # loop 2 — must NOT reuse them

    # A third, for luck: the pool must keep working, not merely fail differently.
    asyncio.run(_use(pool))


def test_a_worker_thread_with_its_own_loop_gets_its_own_connection() -> None:
    """The production shape of the same bug: a sentinel or an instrument doing
    `asyncio.run()` on a pooled worker thread, against the global pool."""
    pool = SurrealPool(max_connections=2)

    asyncio.run(_use(pool))  # main thread, loop 1

    errors: list[BaseException] = []

    def worker() -> None:
        try:
            asyncio.run(_use(pool))  # worker thread, loop 2 — different loop entirely
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=30)

    assert not errors, f"a worker thread got a connection bound to another loop: {errors[0]!r}"


@pytest.mark.asyncio
async def test_the_pool_still_reuses_connections_on_the_SAME_loop() -> None:
    """The fix must not turn the pool into a connection factory.

    Asserting the connection OBJECT is the same is wrong — with two connections the pool
    legitimately rotates between them. The property that matters is that a same-loop
    acquire creates no NEW connection; otherwise we have traded a correctness bug for a
    performance one and nothing would say so.
    """
    pool = SurrealPool(max_connections=2)

    async with pool.connection() as db:
        await db.query("RETURN 1")
    created_after_warmup = pool._total_created

    for _ in range(5):
        async with pool.connection() as db:
            await db.query("RETURN 1")

    assert pool._total_created == created_after_warmup, (
        f"the pool opened {pool._total_created - created_after_warmup} new connections for "
        f"five same-loop acquires — it is behaving as a factory, not a pool"
    )
