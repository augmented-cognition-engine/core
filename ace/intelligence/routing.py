"""Pure interpretation of exact, activation-bound attention-routing policy."""

from __future__ import annotations

from dataclasses import dataclass

from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    IntelligenceResourceMode,
    SignalV1Alpha1,
)
from ace.intelligence.packs.runtime import (
    PreparedActivationBinding,
    PreparedActivationBindingError,
    resolve_persona_modules,
    validate_prepared_activation_binding,
)


class SignalRoutingError(ValueError):
    """A Signal cannot be evaluated under the supplied prepared binding."""


@dataclass(frozen=True, slots=True)
class EligibleSignalRoute:
    """Ephemeral bound route selection; this is not a durable execution or audit receipt."""

    activation_revision: ActivationRevisionReferenceV1Alpha1
    routing_rule_id: str
    persona_ids: tuple[str, ...]
    brief_template_id: str | None


def _revalidate_signal(signal: SignalV1Alpha1) -> SignalV1Alpha1:
    try:
        return SignalV1Alpha1.model_validate(signal.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SignalRoutingError("Signal failed exact resource revalidation") from exc


def _eligible_signal_routes(
    *,
    binding: PreparedActivationBinding,
    signal: SignalV1Alpha1,
    expected_mode: IntelligenceResourceMode,
) -> tuple[EligibleSignalRoute, ...]:
    """Return deterministic routes resolved only from exact Pack IR."""

    try:
        validated_binding = validate_prepared_activation_binding(binding)
        persona_modules = resolve_persona_modules(validated_binding)
    except PreparedActivationBindingError as exc:
        raise SignalRoutingError(str(exc)) from exc
    validated_signal = _revalidate_signal(signal)
    if validated_signal.mode is not expected_mode:
        raise SignalRoutingError(f"{expected_mode.value} routing can interpret only {expected_mode.value} Signals")
    if validated_signal.activation_revision != validated_binding.reference:
        raise SignalRoutingError("Signal does not use the exact bound activation revision")
    if validated_signal.product_id != validated_binding.revision.spec.product_id:
        raise SignalRoutingError("Signal is outside the bound product scope")
    if validated_signal.as_of < validated_binding.revision.occurred_at:
        raise SignalRoutingError("Signal predates the prepared activation revision")

    routes = (
        route
        for module in persona_modules
        for route in module.signal_routing_rules
        if route.signal_type == validated_signal.signal_type_ref
        and validated_signal.confidence >= route.minimum_confidence
    )
    return tuple(
        EligibleSignalRoute(
            activation_revision=validated_binding.reference,
            routing_rule_id=route.routing_rule_id,
            persona_ids=route.persona_ids,
            brief_template_id=route.brief_template_id,
        )
        for route in sorted(routes, key=lambda item: item.routing_rule_id)
    )


def eligible_signal_routes(
    *,
    binding: PreparedActivationBinding,
    signal: SignalV1Alpha1,
) -> tuple[EligibleSignalRoute, ...]:
    """Return deterministic routes for one PREPARED Signal only."""

    return _eligible_signal_routes(
        binding=binding,
        signal=signal,
        expected_mode=IntelligenceResourceMode.PREPARED,
    )


def eligible_live_signal_routes(
    *,
    binding: PreparedActivationBinding,
    signal: SignalV1Alpha1,
) -> tuple[EligibleSignalRoute, ...]:
    """Return deterministic routes for one LIVE Signal; never delivery authority."""

    return _eligible_signal_routes(
        binding=binding,
        signal=signal,
        expected_mode=IntelligenceResourceMode.LIVE,
    )
