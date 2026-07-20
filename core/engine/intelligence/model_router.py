# engine/intelligence/model_router.py
"""Model routing for the intelligence pipeline.

Delegates to engine.runtime.model_config.route_model so that intelligence
modules can import from a stable local path without duplicating logic.
"""

from __future__ import annotations

from core.engine.runtime.model_config import route_model  # noqa: F401

__all__ = ["route_model"]
