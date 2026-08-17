"""Installed Code Intelligence composition for generic ACE host seams."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from core.engine.version import VERSION

if TYPE_CHECKING:
    from core.engine.extensions.registry import Registry


def _installed_core_version() -> str:
    try:
        return version("ace-core")
    except PackageNotFoundError:
        return VERSION


def _atrium_code_lens_reader(records: Any) -> Any:
    """Construct the adapter without importing it into the generic host."""

    from core.engine.code_intelligence.resource_plane import AtriumCodeLensResourceProjectionReader

    return AtriumCodeLensResourceProjectionReader(store=records)


class CodeIntelligenceSolution:
    """Register the optional Code lens on existing provider-neutral seams."""

    name = "code-intelligence"
    version = _installed_core_version()

    def register(self, reg: "Registry") -> None:
        reg.register_intelligence_resource_projection_provider(
            "atrium-code-lens",
            _atrium_code_lens_reader,
            supported_kinds=frozenset({"semantic_revision"}),
        )


__all__ = ["CodeIntelligenceSolution"]
