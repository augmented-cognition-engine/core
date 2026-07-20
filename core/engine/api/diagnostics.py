# engine/api/diagnostics.py
"""Diagnostics API — system health endpoint consumed by the portal health page.

GET /health/system  →  JSON with per-probe results, mirroring ace_diagnostics MCP tool.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["diagnostics"])


@router.get("/system")
async def get_system_health(product: str = "product:platform") -> dict:
    """Run real probes on every ACE subsystem and return structured results.

    Used by the portal System Health page (polls every 30s).
    Each probe has a 2-second timeout and never raises.
    """
    from core.engine.mcp.tools import ace_diagnostics

    return await ace_diagnostics(product_id=product)
