# engine/sentinel/registry.py
"""Engine registry — decorator-based registration for sentinel engines.

Engines register at import time. The registry maps engine name to
(async function, cron expression, description). No DB access.

Spec: docs/superpowers/specs/2026-03-21-phase3a-scheduler-signals.md §2
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

# Global registry: name -> { fn, cron, description }
engine_registry: dict[str, dict[str, Any]] = {}


def register_engine(
    name: str,
    cron: str,
    description: str,
    trigger: Callable[[str], Any] | None = None,
) -> Callable:
    """Decorator to register a sentinel engine.

    Args:
        name: Unique engine identifier.
        cron: Crontab expression for the scheduler.
        description: Short human description.
        trigger: Optional async predicate `(product_id) -> bool`. When provided,
            the scheduler calls it before invoking the engine. False skips the
            engine and records a `sentinel_engine_total{status="skipped"}` metric.
            None (default) preserves today's always-run behavior.

    Usage:
        @register_engine(name="briefing", cron="0 6 * * 1",
                         description="Weekly briefing",
                         trigger=meaningful_change_since_last_run)
        async def run(product_id: str) -> dict: ...
    """

    def decorator(fn: Callable[[str], Coroutine[Any, Any, dict]]) -> Callable:
        if name in engine_registry:
            if engine_registry[name]["fn"] is fn:
                return fn
            raise ValueError(f"Engine '{name}' already registered")
        engine_registry[name] = {
            "fn": fn,
            "cron": cron,
            "description": description,
            "trigger": trigger,
        }
        return fn

    return decorator


def get_engine(name: str) -> dict[str, Any] | None:
    """Return registry entry for the given engine name, or None."""
    return engine_registry.get(name)


def list_engines() -> list[dict[str, str]]:
    """Return metadata for all registered engines (no fn reference)."""
    return [
        {
            "name": name,
            "cron": entry["cron"],
            "description": entry["description"],
            "has_trigger": entry.get("trigger") is not None,
        }
        for name, entry in engine_registry.items()
    ]
