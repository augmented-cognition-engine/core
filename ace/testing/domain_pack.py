"""Public provider-free golden-fixture conformance for third-party Domain Packs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC
from typing import Any

from pydantic import ValidationError

from ace.core.contracts import canonical_hash, canonical_json
from ace.intelligence.contracts.activation import (
    ActivationState,
    CompiledPackRefV1,
    DomainActivationRevisionV1,
    DomainActivationSpecV1,
    OrganizationOverlayV1,
)
from ace.intelligence.contracts.common import MAX_RESOURCE_BYTES, parse_json_strict
from ace.intelligence.contracts.conformance import (
    DomainPackConformanceReceiptV1,
    DomainPackGoldenFixtureV1,
    GoldenDetectorOutcomeV1,
)
from ace.intelligence.contracts.detection import (
    DETECTION_MODULE_V1ALPHA2_VERSION,
    DETECTION_MODULE_VERSION,
    DetectionModuleV1,
    DetectionModuleV1Alpha2,
    NumericDeltaRuleV1,
)
from ace.intelligence.contracts.resources import (
    CanonicalJsonValueV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
)
from ace.intelligence.detection.categorical_transition import (
    detect_categorical_shift,
    route_categorical_shift_as_signal,
)
from ace.intelligence.detection.numeric_delta import detect_numeric_shift, route_shift_as_signal
from ace.intelligence.packs.activation import compile_overlay
from ace.intelligence.packs.compiler import compile_pack_document_with_report
from ace.intelligence.packs.diagnostics import PackDiagnosticV1
from ace.intelligence.packs.runtime import bind_prepared_activation, resolve_entity_type_declaration
from ace.intelligence.routing import eligible_signal_routes


def _digest(value: Any) -> str:
    return f"sha256:{canonical_hash(value)}"


def _fixture(document: bytes) -> DomainPackGoldenFixtureV1:
    if not isinstance(document, bytes):
        raise TypeError("fixture document must be bytes")
    if len(document) > MAX_RESOURCE_BYTES:
        raise ValueError(f"fixture exceeds the {MAX_RESOURCE_BYTES}-byte bound")
    try:
        payload = parse_json_strict(document.decode("utf-8"))
        return DomainPackGoldenFixtureV1.model_validate(payload)
    except (UnicodeDecodeError, ValueError, ValidationError, RecursionError) as exc:
        raise ValueError("fixture must be strict UTF-8 JSON matching the stable golden-fixture schema") from exc


def _binding(pack, fixture: DomainPackGoldenFixtureV1):
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="pack_conformance",
            version=fixture.fixture_version,
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
            values=fixture.overlay_values,
        ),
    )
    pack_ref = CompiledPackRefV1(
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
    )
    occurred_at = min(item.baseline_as_of for item in fixture.observations).astimezone(UTC)
    spec = DomainActivationSpecV1(
        product_id="product:pack-conformance",
        activation_key=pack.metadata.pack_id,
        pack=pack_ref,
        overlay=overlay,
        compilation_receipt_ref=f"compilation:{pack.pack_digest.removeprefix('sha256:')[:32]}",
        conformance_receipt_refs=("conformance:pending",),
    )
    revision = DomainActivationRevisionV1(
        revision=1,
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:pack-conformance",
        approval_receipt_ref="approval:pack-conformance-ephemeral",
        occurred_at=occurred_at,
    )
    return bind_prepared_activation(pack=pack, revision=revision)


def _detector_rules(pack) -> tuple[Any, ...]:
    models = {
        DETECTION_MODULE_VERSION: DetectionModuleV1,
        DETECTION_MODULE_V1ALPHA2_VERSION: DetectionModuleV1Alpha2,
    }
    rules: list[Any] = []
    for module in pack.modules:
        model = models.get(module.contract)
        if model is None:
            continue
        parsed = model.model_validate_json(module.canonical_payload)
        rules.extend(parsed.numeric_delta_rules)
        rules.extend(getattr(parsed, "categorical_transition_rules", ()))
    return tuple(sorted(rules, key=lambda item: item.detector_id))


def _outcomes(pack, fixture: DomainPackGoldenFixtureV1) -> tuple[dict[str, Any], ...]:
    binding = _binding(pack, fixture)
    rules = _detector_rules(pack)
    results: list[dict[str, Any]] = []
    for case in fixture.observations:
        resolve_entity_type_declaration(binding, entity_type_id=case.entity_type_id)
        baseline = EntitySnapshotV1Alpha1(
            product_id=binding.reference.product_id,
            mode=IntelligenceResourceMode.PREPARED,
            activation_revision=binding.reference,
            as_of=case.baseline_as_of,
            entity_ref=case.entity_ref,
            entity_type_ref=case.entity_type_id,
            attributes=CanonicalJsonValueV1Alpha1(value_json=case.baseline_attributes_json),
            projected_at=case.baseline_as_of,
            confidence=case.confidence,
        )
        current = EntitySnapshotV1Alpha1(
            product_id=binding.reference.product_id,
            mode=IntelligenceResourceMode.PREPARED,
            activation_revision=binding.reference,
            as_of=case.current_as_of,
            entity_ref=case.entity_ref,
            entity_type_ref=case.entity_type_id,
            attributes=CanonicalJsonValueV1Alpha1(value_json=case.current_attributes_json),
            projected_at=case.current_as_of,
            confidence=case.confidence,
        )
        case_outcomes: list[GoldenDetectorOutcomeV1] = []
        for rule in rules:
            if rule.entity_type_id != case.entity_type_id:
                continue
            if isinstance(rule, NumericDeltaRuleV1):
                shift = detect_numeric_shift(
                    binding=binding,
                    detector_id=rule.detector_id,
                    baseline=baseline,
                    current=current,
                    detected_at=case.current_as_of,
                )
                signal = None if shift is None else route_shift_as_signal(
                    binding=binding,
                    detector_id=rule.detector_id,
                    shift=shift,
                    detected_at=case.current_as_of,
                )
            else:
                shift = detect_categorical_shift(
                    binding=binding,
                    detector_id=rule.detector_id,
                    baseline=baseline,
                    current=current,
                    detected_at=case.current_as_of,
                )
                signal = None if shift is None else route_categorical_shift_as_signal(
                    binding=binding,
                    detector_id=rule.detector_id,
                    shift=shift,
                    detected_at=case.current_as_of,
                )
            routes = () if signal is None else eligible_signal_routes(binding=binding, signal=signal)
            case_outcomes.append(
                GoldenDetectorOutcomeV1(
                    detector_id=rule.detector_id,
                    entity_ref=case.entity_ref,
                    material=shift is not None,
                    shift_type=None if shift is None else shift.shift_type_ref,
                    signal_type=None if signal is None else signal.signal_type_ref,
                    routing_rule_ids=tuple(route.routing_rule_id for route in routes),
                    persona_ids=tuple(sorted({persona for route in routes for persona in route.persona_ids})),
                    template_ids=tuple(
                        sorted({route.brief_template_id for route in routes if route.brief_template_id is not None})
                    ),
                )
            )
        results.append(
            {
                "case_id": case.case_id,
                "outcomes": [item.model_dump(mode="json") for item in sorted(case_outcomes, key=lambda x: x.detector_id)],
            }
        )
    return tuple(results)


def run_domain_pack_conformance(
    *,
    manifest_document: bytes,
    resources: Mapping[str, bytes],
    fixture_document: bytes,
    prior_receipt: DomainPackConformanceReceiptV1 | None = None,
) -> DomainPackConformanceReceiptV1:
    """Compile and exercise one pack without providers, network, persistence, or a database."""

    compiled = compile_pack_document_with_report(manifest_document, resources)
    pack = compiled.pack
    fixture = _fixture(fixture_document)
    fixture_material = fixture.model_dump(mode="json")
    fixture_digest = _digest(fixture_material)
    expected = tuple(
        {
            "case_id": case.case_id,
            "outcomes": [item.model_dump(mode="json") for item in case.expected],
        }
        for case in fixture.observations
    )
    diagnostics: list[PackDiagnosticV1] = []
    try:
        actual = _outcomes(pack, fixture)
    except (TypeError, ValueError) as exc:
        actual = ()
        diagnostics.append(
            PackDiagnosticV1(
                severity="error",
                code="conformance_runtime_error",
                path="fixture.observations",
                message=str(exc)[:1_000] or "golden-fixture evaluation failed",
            )
        )
    if prior_receipt is not None and prior_receipt.fixture_id == fixture.fixture_id and (
        prior_receipt.fixture_digest != fixture_digest or prior_receipt.expected_digest != _digest(expected)
    ):
        diagnostics.append(
            PackDiagnosticV1(
                severity="error",
                code="divergent_conformance_identity",
                path="fixture.fixture_id",
                message="the same fixture identity cannot name changed fixture or expected-result material",
            )
        )
    if actual != expected:
        diagnostics.append(
            PackDiagnosticV1(
                severity="error",
                code="golden_result_mismatch",
                path="fixture.observations",
                message="derived entity, Shift, Signal, routing, persona, or synthesis selection differs from the golden result",
            )
        )
    expected_digest = _digest(expected)
    actual_digest = _digest(actual)
    return DomainPackConformanceReceiptV1(
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
        manifest_contract=pack.manifest_contract,
        compiler_contract=pack.compiler_contract,
        intelligence_contract=pack.intelligence_contract,
        compatibility_status=compiled.compatibility.status,
        compilation_result_id=compiled.compilation.result_id,
        compilation_result_digest=compiled.compilation.result_digest,
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_digest=fixture_digest,
        expected_digest=expected_digest,
        actual_digest=actual_digest,
        passed=not diagnostics,
        diagnostics=tuple(diagnostics),
    )


def conformance_receipt_json(receipt: DomainPackConformanceReceiptV1) -> str:
    """Return the exact portable receipt representation used for byte comparisons."""

    return canonical_json(receipt)


__all__ = ["conformance_receipt_json", "run_domain_pack_conformance"]
