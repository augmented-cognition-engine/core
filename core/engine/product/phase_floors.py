"""Phase floors at pillar level + product-type and scale modifier composition.

Per docs/discipline-taxonomy.md v1.6 floor curves and modifiers.
"""

from __future__ import annotations

from core.engine.product.pillars import Pillar

DEFAULT_PILLAR_FLOORS: dict[tuple[Pillar, str], float] = {
    (Pillar.EXPERIENCE, "discovery"): 0.4,
    (Pillar.EXPERIENCE, "poc"): 0.55,
    (Pillar.EXPERIENCE, "alpha"): 0.7,
    (Pillar.EXPERIENCE, "beta"): 0.8,
    (Pillar.EXPERIENCE, "ga"): 0.9,
    (Pillar.EXPERIENCE, "mature"): 0.92,
    (Pillar.INTERFACE, "discovery"): 0.3,
    (Pillar.INTERFACE, "poc"): 0.5,
    (Pillar.INTERFACE, "alpha"): 0.65,
    (Pillar.INTERFACE, "beta"): 0.75,
    (Pillar.INTERFACE, "ga"): 0.85,
    (Pillar.INTERFACE, "mature"): 0.88,
    (Pillar.LOGIC, "discovery"): 0.5,
    (Pillar.LOGIC, "poc"): 0.6,
    (Pillar.LOGIC, "alpha"): 0.7,
    (Pillar.LOGIC, "beta"): 0.8,
    (Pillar.LOGIC, "ga"): 0.85,
    (Pillar.LOGIC, "mature"): 0.88,
    (Pillar.STATE, "discovery"): 0.4,
    (Pillar.STATE, "poc"): 0.55,
    (Pillar.STATE, "alpha"): 0.7,
    (Pillar.STATE, "beta"): 0.8,
    (Pillar.STATE, "ga"): 0.85,
    (Pillar.STATE, "mature"): 0.88,
    (Pillar.OPERATIONS, "discovery"): 0.2,
    (Pillar.OPERATIONS, "poc"): 0.35,
    (Pillar.OPERATIONS, "alpha"): 0.55,
    (Pillar.OPERATIONS, "beta"): 0.7,
    (Pillar.OPERATIONS, "ga"): 0.85,
    (Pillar.OPERATIONS, "mature"): 0.9,
    (Pillar.EVOLUTION, "discovery"): 0.3,
    (Pillar.EVOLUTION, "poc"): 0.45,
    (Pillar.EVOLUTION, "alpha"): 0.6,
    (Pillar.EVOLUTION, "beta"): 0.75,
    (Pillar.EVOLUTION, "ga"): 0.85,
    (Pillar.EVOLUTION, "mature"): 0.88,
    (Pillar.TRUST, "discovery"): 0.2,
    (Pillar.TRUST, "poc"): 0.4,
    (Pillar.TRUST, "alpha"): 0.6,
    (Pillar.TRUST, "beta"): 0.75,
    (Pillar.TRUST, "ga"): 0.9,
    (Pillar.TRUST, "mature"): 0.95,
}


PRODUCT_TYPE_MODIFIERS: dict[tuple[str, Pillar, str], float] = {
    ("ai_native", Pillar.EXPERIENCE, "poc"): 0.15,
    ("ai_native", Pillar.LOGIC, "poc"): 0.10,
    ("ai_native", Pillar.EVOLUTION, "poc"): 0.10,
    ("ai_native", Pillar.EXPERIENCE, "ga"): 0.05,
    ("ai_native", Pillar.TRUST, "ga"): 0.10,
    ("trading_system", Pillar.LOGIC, "poc"): 0.15,
    ("trading_system", Pillar.OPERATIONS, "poc"): 0.15,
    ("trading_system", Pillar.TRUST, "poc"): 0.10,
    ("trading_system", Pillar.OPERATIONS, "ga"): 0.05,
    ("trading_system", Pillar.TRUST, "ga"): 0.05,
    ("mobile_consumer_app", Pillar.EXPERIENCE, "poc"): 0.10,
    ("mobile_consumer_app", Pillar.OPERATIONS, "poc"): 0.05,
    ("mobile_consumer_app", Pillar.TRUST, "poc"): 0.05,
    ("internal_tool", Pillar.EXPERIENCE, "poc"): -0.10,
    ("internal_tool", Pillar.EXPERIENCE, "ga"): -0.05,
    ("internal_tool", Pillar.OPERATIONS, "ga"): 0.05,
    ("content_site", Pillar.EXPERIENCE, "poc"): 0.10,
    ("content_site", Pillar.INTERFACE, "poc"): 0.10,
    ("content_site", Pillar.OPERATIONS, "ga"): 0.05,
    ("ecommerce", Pillar.EXPERIENCE, "poc"): 0.10,
    ("ecommerce", Pillar.INTERFACE, "poc"): 0.05,
    ("ecommerce", Pillar.TRUST, "poc"): 0.05,
    ("dev_tool", Pillar.INTERFACE, "poc"): 0.15,
    ("dev_tool", Pillar.EVOLUTION, "poc"): 0.10,
    ("enterprise_ds", Pillar.STATE, "poc"): 0.15,
    ("enterprise_ds", Pillar.LOGIC, "poc"): 0.10,
    ("enterprise_ds", Pillar.TRUST, "poc"): 0.10,
    ("enterprise_ds", Pillar.STATE, "ga"): 0.05,
    ("enterprise_ds", Pillar.TRUST, "ga"): 0.10,
    ("mobile_game", Pillar.EXPERIENCE, "poc"): 0.15,
    ("mobile_game", Pillar.OPERATIONS, "poc"): 0.05,
    ("mobile_game", Pillar.EXPERIENCE, "ga"): 0.05,
}


SCALE_MODIFIERS: dict[tuple[str, Pillar], float] = {
    ("atomic", Pillar.EXPERIENCE): 0.0,
    ("atomic", Pillar.INTERFACE): -0.2,
    ("atomic", Pillar.LOGIC): 0.0,
    ("atomic", Pillar.STATE): -0.3,
    ("atomic", Pillar.OPERATIONS): -0.4,
    ("atomic", Pillar.EVOLUTION): -0.3,
    ("atomic", Pillar.TRUST): -0.4,
    ("component", Pillar.EXPERIENCE): -0.1,
    ("component", Pillar.INTERFACE): 0.1,
    ("component", Pillar.STATE): -0.1,
    ("component", Pillar.OPERATIONS): -0.1,
    ("component", Pillar.EVOLUTION): 0.05,
    ("component", Pillar.TRUST): -0.1,
    ("application", Pillar.EXPERIENCE): 0.0,
    ("application", Pillar.INTERFACE): 0.0,
    ("application", Pillar.LOGIC): 0.0,
    ("application", Pillar.STATE): 0.0,
    ("application", Pillar.OPERATIONS): 0.0,
    ("application", Pillar.EVOLUTION): 0.0,
    ("application", Pillar.TRUST): 0.0,
    ("platform", Pillar.INTERFACE): 0.1,
    ("platform", Pillar.STATE): 0.05,
    ("platform", Pillar.OPERATIONS): 0.1,
    ("platform", Pillar.EVOLUTION): 0.1,
    ("platform", Pillar.TRUST): 0.1,
    ("enterprise", Pillar.INTERFACE): 0.05,
    ("enterprise", Pillar.LOGIC): 0.05,
    ("enterprise", Pillar.STATE): 0.1,
    ("enterprise", Pillar.OPERATIONS): 0.1,
    ("enterprise", Pillar.EVOLUTION): 0.1,
    ("enterprise", Pillar.TRUST): 0.2,
}


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def effective_floor(
    pillar: Pillar,
    phase: str,
    product_type: str,
    scale: str,
    custom_override: float | None = None,
) -> float:
    """Compose the effective floor from default + type modifier + scale modifier + override."""
    if custom_override is not None:
        return _clip(custom_override)

    base = DEFAULT_PILLAR_FLOORS.get((pillar, phase), 0.0)
    type_delta = PRODUCT_TYPE_MODIFIERS.get((product_type, pillar, phase), 0.0)
    scale_delta = SCALE_MODIFIERS.get((scale, pillar), 0.0)
    return _clip(base + type_delta + scale_delta)
