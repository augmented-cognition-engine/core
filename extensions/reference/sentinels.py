"""A worked sentinel-engine example — the 24/7 extension point.

A sentinel is ``async def (product_id: str) -> dict`` that the kernel
scheduler runs on a cron, whether or not the user is present. Real
sentinels read the DB (acquire from ``core.engine.core.db.pool``) and
write findings/insights; this example stays side-effect-free so every
fresh install runs clean. A production sentinel does the same thing
against its own domain tables.
"""

from __future__ import annotations


async def run_product_heartbeat(product_id: str = "product:platform") -> dict:
    """Daily no-op heartbeat proving the extension's sentinel is scheduled."""
    from core.engine.sentinel.registry import list_engines

    return {
        "product": product_id,
        "engines_visible": len(list_engines()),
        "source": "extensions.reference",
    }
