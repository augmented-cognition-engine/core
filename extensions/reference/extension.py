"""ProductExtension — the canonical ACE extension.

If you want ACE to deliberate in your own domain's terms, write an extension. This
file is the complete worked example, designed to be copied as your starting point.
Every extension point the kernel consumes is implemented or shown as a commented
one-liner.

When this extension is installed, dropping a product thought into the playground
convenes a problem-fit partner team for product decisions: a PM, a Skeptic, and a
User-Advocate (using ACE's generic archetypes) reason through the decision in
parallel, then synthesize a recommendation bound by kill criteria.

Discovered via the ``ace.extensions`` entry point in pyproject:

    [project.entry-points."ace.extensions"]
    product = "extensions.reference.extension:ProductExtension"

Four live extension points are demonstrated below. Five additional Registry
points (committee, personas, frameworks, schema, briefing-section) are shown
as commented one-liners so a contributor copying this file sees the FULL
extension surface in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.engine.extensions.registry import Registry


# slug -> module path. Instruments live alongside this extension under
# extensions/reference/instruments/. The extension registers them; the kernel
# doesn't need to know they exist.
_INSTRUMENTS: dict[str, str] = {
    "product-framing": "extensions.reference.instruments.framing",
    "multi-voice-engage": "extensions.reference.instruments.multi_voice_engage",
}


class ProductExtension:
    """The open `product` extension — copy this file to start your own."""

    name = "product"
    version = "0.1.2"

    def register(self, reg: "Registry") -> None:
        # --- 1. Instruments — bespoke LLM pipeline steps used by the recipe ----
        for slug, module_path in _INSTRUMENTS.items():
            reg.register_instrument(slug, module_path)

        # --- 2. Recipe + routing — the meta-skill the composer selects when ---
        # classification.discipline == "product". The kernel's CognitiveComposer
        # reads registered_recipe_disciplines() and uses this to route.
        reg.register_recipe(
            "product_decision_intelligence",
            "extensions.reference.recipe",
            disciplines=["product"],
        )

        # --- 3. MCP tool — registered onto the kernel MCP server at startup. ---
        # The MCP server reads registered_tools() and exposes each over MCP so
        # external clients can call the extension's tools the same way they call
        # kernel tools.
        from extensions.reference.tools.product_pulse import ace_product_pulse

        reg.register_tool(ace_product_pulse, title="Product Pulse")

        # --- 4. Sentinel engine — a 24/7 engine the kernel scheduler runs ---
        # on a cron, whether or not the user is present. Extension sentinels
        # land in the same engine registry as kernel engines: they appear in
        # list_engines(), honor per-product schedule overrides, and emit the
        # same metrics.
        from extensions.reference.sentinels import run_product_heartbeat

        reg.register_sentinel(
            "product_heartbeat",
            cron="0 6 * * *",
            description="Daily heartbeat from the product extension (worked example)",
            fn=run_product_heartbeat,
        )

        # --- The remaining Registry points (shown so a contributor sees the
        # full extension surface). Uncomment when you need them; the kernel
        # consumes some today and not others — see the spec for the live audit.

        # Committee — extensions can register named committee builders. The kernel
        # does not yet consume registered_committees() (the deep committee
        # resolves lenses dynamically); a future plan wires this in.
        # reg.register_committee("product_council", _lazy_committee("product_council"))

        # Personas — extensions can contribute domain-specific persona models.
        # Not yet consumed by the open kernel.
        # reg.register_personas([MyDomainPersona(...)])

        # Frameworks — extensions can contribute reasoning frameworks (system prompts).
        # Not yet consumed by the open kernel.
        # reg.register_frameworks([MyFramework(...)])

        # Schema — extensions can ship .surql migrations for their own tables.
        # Not yet consumed by the open kernel; bring your own migration runner.
        # reg.register_schema("extensions/reference/schema/v01_product_tables.surql")

        # Briefing section — extensions can contribute sections to the daily sentinel
        # briefing. The kernel DOES consume this (engine/sentinel/engines/briefing.py),
        # but the open `product` extension has no product-specific data to add
        # beyond what the kernel briefing already shows. A production extension
        # would register a builder that reads its own domain metrics.
        # reg.register_briefing_section(build_product_briefing, metrics_key="product_health")
