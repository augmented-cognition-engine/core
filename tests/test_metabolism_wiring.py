"""Reachability guards for the grounding metabolism drainer (no DB).

Sentinel engines register via a @register_engine decorator that fires ONLY when
the module is imported, and engine_registry is populated ONLY by the explicit
imports in core/engine/api/main.py (pkgutil discovery was deliberately removed).
A forgotten import means the engine silently never schedules — the exact
"unregistered engine" class this repo has been bitten by. These fast-lane tests
fail loudly if that wiring regresses.
"""

from __future__ import annotations

from pathlib import Path


def test_metabolism_drainer_registers_via_decorator():
    import core.engine.sentinel.engines.metabolism_drainer  # noqa: F401 — fires @register_engine
    from core.engine.sentinel.registry import get_engine

    entry = get_engine("metabolism_drainer")
    assert entry is not None, "metabolism_drainer did not register"
    assert entry.get("cron") == "*/15 * * * *"


def test_metabolism_drainer_is_imported_by_main_startup():
    """The decorator is inert unless main.py imports the module at startup."""
    main_src = Path("core/engine/api/main.py").read_text()
    assert "core.engine.sentinel.engines.metabolism_drainer" in main_src, (
        "metabolism_drainer is not imported in main.py — it will never register with the scheduler"
    )


async def test_ace_rederive_tool_is_registered_on_the_mcp_server():
    """The re-derivation's partner invoker — a @mcp.tool that must actually register
    (a duplicate name silently shadows under FastMCP)."""
    from core.engine.mcp.server import mcp

    tool = await mcp.get_tool("ace_rederive")
    assert tool is not None, "ace_rederive not registered — the metabolism has no partner invoker"
