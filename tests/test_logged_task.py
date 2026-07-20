# tests/test_logged_task.py
"""Tests for logged_task() — safe asyncio.create_task() wrapper."""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_logged_task_success_runs_coroutine():
    """A successful coroutine completes normally."""
    from core.engine.core.tasks import logged_task

    ran = []

    async def _work():
        ran.append(True)

    t = logged_task(_work(), label="test.success")
    await t
    assert ran == [True]


@pytest.mark.asyncio
async def test_logged_task_exception_records_to_error_buffer():
    """Exception in coroutine is captured to error_buffer, not silently dropped."""
    from core.engine.core.error_buffer import error_buffer
    from core.engine.core.tasks import logged_task

    error_buffer.clear()

    async def _boom():
        raise RuntimeError("task failed")

    t = logged_task(_boom(), label="test.boom")
    # Two yields: first lets the task run, second lets the done callback fire
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    recent = error_buffer.recent(5)
    assert any(e["source"] == "background_task.test.boom" and "task failed" in e["message"] for e in recent), (
        f"Expected error in buffer, got: {recent}"
    )


@pytest.mark.asyncio
async def test_logged_task_exception_does_not_propagate():
    """Exception in background task must NOT propagate to the caller context."""
    from core.engine.core.tasks import logged_task

    async def _boom():
        raise ValueError("silent")

    # Must not raise — done callback absorbs the exception
    t = logged_task(_boom(), label="test.silent")
    await asyncio.sleep(0)
    assert t.done()


@pytest.mark.asyncio
async def test_logged_task_logs_error():
    """Exception in background task is logged at ERROR level via a custom handler."""
    import logging

    from core.engine.core.tasks import logged_task

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture(level=logging.ERROR)
    log = logging.getLogger("core.engine.core.tasks")
    log.addHandler(handler)
    try:

        async def _boom():
            raise TypeError("logged error")

        t = logged_task(_boom(), label="test.log")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        log.removeHandler(handler)

    assert any("logged error" in r.getMessage() for r in records)
