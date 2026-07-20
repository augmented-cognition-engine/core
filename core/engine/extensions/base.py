"""The Extension contract — the extension point for building domain extensions on ACE.

An extension packages domain config (personas, frameworks, recipes, instruments,
MCP tools, schema) and registers it on the kernel WITHOUT forking. Extensions are
discovered via the ``ace.extensions`` entry-point group (see ``loader.py``).

Test for "belongs in an extension": would it be useless to a different domain? If
yes, it's extension config — not kernel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.engine.extensions.registry import Registry


@runtime_checkable
class Extension(Protocol):
    """A domain extension. Implementations live in their own package and expose
    themselves via the ``ace.extensions`` entry point.

    Example::

        class MarketingExtension:
            name = "marketing"
            version = "0.1.0"

            def register(self, reg: "Registry") -> None:
                reg.register_instrument("b2b-buying-committee",
                                        "ace_extension_marketing.instruments.buying_committee")
                reg.register_committee("buying_committee", buying_committee)
                reg.register_personas(BUYER_PERSONAS)
                reg.register_schema("ace_extension_marketing/schema/marketing.surql")
    """

    name: str
    version: str

    def register(self, reg: "Registry") -> None:
        """Wire every capability this extension contributes, via the registry facade."""
        ...
