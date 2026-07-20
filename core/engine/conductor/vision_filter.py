# engine/conductor/vision_filter.py
"""Vision/theme alignment filter.

Ensures the conductor only works on capabilities aligned with
the active vision and themes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SAFETY_DIMENSIONS = {"security", "error_handling"}


class VisionFilter:
    """Filter conductor work by vision/theme alignment."""

    def __init__(self, db_pool) -> None:
        self._pool = db_pool

    async def is_aligned(self, context: dict) -> bool:
        """Check if the work implied by this context aligns with vision/themes.

        Permissive rules:
        - No themes set -> everything passes
        - No capability in context -> passes (non-capability events)
        - Critical priority -> always passes
        - Safety dimensions (security, error_handling) -> always passes
        - Otherwise: capability tags must intersect with theme names
        """
        capability = context.get("capability")
        if not capability:
            return True

        themes = context.get("themes") or []
        if not themes:
            return True

        # Critical priority always passes
        if capability.get("priority") == "critical":
            return True

        # Safety dimensions always pass
        dimension = context.get("track", {}).get("dimension", "")
        if dimension in SAFETY_DIMENSIONS:
            return True

        # Check tag alignment with themes
        cap_tags = set(t.lower() for t in (capability.get("tags") or []))
        theme_names = set()
        for theme in themes:
            name = theme.get("name", "").lower().replace(" ", "_")
            if name:
                theme_names.add(name)

        if cap_tags & theme_names:
            return True

        return False
