"""Explicit compatibility gate for the pre-Domain-Pack intelligence engines.

These modules predate the public ``ace.intelligence`` lifecycle and encode ACE-product
competitive concepts directly in the legacy host.  They remain import-compatible during the
0.8 migration, but the default Intelligence OS runtime must not compose them implicitly.
"""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

LEGACY_PRODUCT_INTELLIGENCE_MODULES = (
    "core.engine.sentinel.engines.community_scanner",
    "core.engine.sentinel.engines.competitive_observer",
    "core.engine.sentinel.engines.github_release_watcher",
    "core.engine.sentinel.engines.whitespace_engine",
)


def register_legacy_product_intelligence_engines(*, enabled: bool) -> tuple[str, ...]:
    """Register the old ACE-product intelligence engines only by explicit opt-in.

    The returned module names are diagnostic compatibility evidence.  Registration remains the
    legacy decorators' responsibility; this seam grants no source, model, or execution authority.
    """

    if not enabled:
        return ()

    logger.warning(
        "Legacy product-intelligence engines are enabled. This compatibility surface is not the "
        "ACE 0.8 Intelligence lifecycle and should be replaced by a Domain Pack plus authorized "
        "connectors."
    )
    for module_name in LEGACY_PRODUCT_INTELLIGENCE_MODULES:
        importlib.import_module(module_name)
    return LEGACY_PRODUCT_INTELLIGENCE_MODULES


__all__ = [
    "LEGACY_PRODUCT_INTELLIGENCE_MODULES",
    "register_legacy_product_intelligence_engines",
]
