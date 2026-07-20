# tests/test_log_context.py
"""Tests for per-request correlation ID context propagation."""

from __future__ import annotations

import asyncio

import pytest

from core.engine.core.log_context import get_correlation_id, new_correlation_id, set_correlation_id


def test_get_returns_empty_string_by_default():
    # ContextVar default is "" — safe to call anywhere
    set_correlation_id("")
    assert get_correlation_id() == ""


def test_set_and_get_roundtrip():
    set_correlation_id("abc123")
    assert get_correlation_id() == "abc123"


def test_new_correlation_id_generates_and_sets():
    cid = new_correlation_id()
    assert len(cid) == 12
    assert cid.isalnum()  # hex chars
    assert get_correlation_id() == cid


def test_new_correlation_id_is_unique():
    cid1 = new_correlation_id()
    cid2 = new_correlation_id()
    assert cid1 != cid2


@pytest.mark.asyncio
async def test_correlation_id_propagates_into_coroutine():
    """ContextVar propagates into awaited coroutines — no manual threading needed."""
    set_correlation_id("parent-cid")

    async def child():
        return get_correlation_id()

    result = await child()
    assert result == "parent-cid"


@pytest.mark.asyncio
async def test_correlation_id_isolated_between_tasks():
    """Each asyncio.create_task() gets its OWN copy — changes don't bleed across tasks."""
    results = {}

    async def task_a():
        set_correlation_id("task-a")
        await asyncio.sleep(0)
        results["a"] = get_correlation_id()

    async def task_b():
        set_correlation_id("task-b")
        await asyncio.sleep(0)
        results["b"] = get_correlation_id()

    await asyncio.gather(asyncio.create_task(task_a()), asyncio.create_task(task_b()))

    assert results["a"] == "task-a"
    assert results["b"] == "task-b"
