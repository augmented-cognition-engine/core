"""Tests for dynamic backgrounding."""

import asyncio

import pytest

from core.engine.runtime.background import BackgroundManager


@pytest.mark.asyncio
async def test_register_and_complete():
    mgr = BackgroundManager()
    completed = []

    async def work():
        await asyncio.sleep(0.01)
        return "done"

    task_id = mgr.register(work(), on_complete=lambda r: completed.append(r))
    assert mgr.is_running(task_id)
    await asyncio.sleep(0.1)
    assert len(completed) == 1
    assert completed[0] == "done"


@pytest.mark.asyncio
async def test_cancel():
    mgr = BackgroundManager()

    async def slow_work():
        await asyncio.sleep(10)
        return "never"

    task_id = mgr.register(slow_work())
    assert mgr.is_running(task_id)
    mgr.cancel(task_id)
    await asyncio.sleep(0.05)
    assert not mgr.is_running(task_id)


@pytest.mark.asyncio
async def test_list_running():
    mgr = BackgroundManager()

    async def work():
        await asyncio.sleep(0.5)

    mgr.register(work(), label="task-a")
    mgr.register(work(), label="task-b")
    running = mgr.list_running()
    assert len(running) == 2
    labels = {r["label"] for r in running}
    assert labels == {"task-a", "task-b"}


def test_empty_manager():
    mgr = BackgroundManager()
    assert mgr.list_running() == []
