"""Pure, deterministic compiler for inert declarative Domain Packs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError

from ace.core.contracts import canonical_hash, canonical_json
from ace.intelligence.contracts.common import MAX_PACK_BYTES, MAX_RESOURCE_BYTES, validate_contract
from ace.intelligence.contracts.detection import (
    DETECTION_MODULE_V1ALPHA2_VERSION,
    DETECTION_MODULE_V1ALPHA3_VERSION,
    DETECTION_MODULE_VERSION,
    DetectionModuleV1,
    DetectionModuleV1Alpha2,
    DetectionModuleV1Alpha3,
)
from ace.intelligence.contracts.epistemic import (
    EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION,
    EPISTEMIC_STATUS_MODULE_VERSION,
    EpistemicStatusModuleV1,
    EpistemicStatusModuleV1Alpha2,
)
from ace.intelligence.contracts.feedback import (
    DECISION_OUTCOMES_MODULE_VERSION,
    DecisionOutcomesModuleV1,
)
from ace.intelligence.contracts.orientation import (
    ORIENTATION_MODULE_VERSION,
    OrientationModuleV1,
)
from ace.intelligence.contracts.pack import (
    COMPILED_DOMAIN_PACK_STABLE_VERSION,
    DOMAIN_PACK_MANIFEST_STABLE_VERSION,
    DOMAIN_PACK_MANIFEST_VERSION,
    INTELLIGENCE_RUNTIME_NEXT_BREAKING_VERSION,
    INTELLIGENCE_RUNTIME_VERSION,
    ONTOLOGY_MODULE_VERSION,
    PACK_COMPILER_NEXT_BREAKING_VERSION,
    PACK_COMPILER_VERSION,
    STABLE_INTELLIGENCE_RUNTIME_VERSION,
    STABLE_PACK_COMPILER_VERSION,
    AttributeValueType,
    CompiledDomainPackV1,
    CompiledModuleV1,
    DomainPackManifestV1,
    OntologyModuleV1,
)
from ace.intelligence.contracts.personas import PERSONAS_MODULE_VERSION, PersonasModuleV1
from ace.intelligence.contracts.source_mapping import (
    SOURCE_MAPPING_MODULE_VERSION,
    SourceMappingModuleV1,
    SourceMappingTransform,
)
from ace.intelligence.contracts.synthesis import (
    SYNTHESIS_MODULE_V1ALPHA2_VERSION,
    SYNTHESIS_MODULE_VERSION,
    SynthesisModuleV1,
    SynthesisModuleV1Alpha2,
)
from ace.intelligence.packs.diagnostics import (
    STABLE_PACK_COMPILATION_REPORT_VERSION,
    PackCompatibilityResultV1,
    PackCompatibilityStatus,
    PackCompilationReportV1,
    PackDiagnosticV1,
    StablePackCompilationResultV1,
)


class PackCompilationError(ValueError):
    """A fail-closed compilation error with stable diagnostics."""

    def __init__(self, report: PackCompilationReportV1) -> None:
        self.report = report
        first = report.diagnostics[0]
        super().__init__(f"{first.code} at {first.path}: {first.message}")


@dataclass(frozen=True, slots=True)
class CompiledPackResultV1:
    pack: CompiledDomainPackV1
    compatibility: PackCompatibilityResultV1
    compilation: StablePackCompilationResultV1


_STABLE_DIAGNOSTICS: ContextVar[bool] = ContextVar("stable_pack_diagnostics", default=False)


def _fail(code: str, path: str, message: str, *, stable: bool = False) -> None:
    bounded_code = str(code)[:120] or "compilation_error"
    bounded_path = str(path)[:500] or "pack"
    bounded_message = str(message)[:1_000] or "pack compilation failed"
    raise PackCompilationError(
        PackCompilationReportV1(
            contract=(
                STABLE_PACK_COMPILATION_REPORT_VERSION
                if stable or _STABLE_DIAGNOSTICS.get()
                else "ace.intelligence.pack-compilation-report/v1alpha1"
            ),
            success=False,
            diagnostics=(
                PackDiagnosticV1(
                    severity="error",
                    code=bounded_code,
                    path=bounded_path,
                    message=bounded_message,
                ),
            ),
        )
    )


def negotiate_pack_compatibility(
    manifest_contract: str,
    compatibility: Mapping[str, Any] | None,
) -> PackCompatibilityResultV1:
    """Negotiate declared contracts against the stable host without package-version inference."""

    try:
        normalized_manifest_contract = validate_contract(manifest_contract)
    except (TypeError, ValueError):
        normalized_manifest_contract = "ace.intelligence.domain-pack-manifest/v0"

    if manifest_contract == DOMAIN_PACK_MANIFEST_VERSION:
        diagnostic = PackDiagnosticV1(
            severity="warning",
            code="deprecated_manifest_contract",
            path="manifest.contract",
            message="v1alpha1 remains supported for the documented prior-version window; migrate offline to v1",
        )
        return PackCompatibilityResultV1(
            manifest_contract=manifest_contract,
            compiler_contract=PACK_COMPILER_VERSION,
            intelligence_contract=INTELLIGENCE_RUNTIME_VERSION,
            status=PackCompatibilityStatus.DEPRECATED,
            diagnostics=(diagnostic,),
        )
    if manifest_contract == DOMAIN_PACK_MANIFEST_STABLE_VERSION:
        declared = compatibility if isinstance(compatibility, Mapping) else {}
        declared_digest = f"sha256:{canonical_hash(dict(declared))}"
        compiler_range = (
            declared.get("compiler_minimum"),
            declared.get("compiler_maximum_exclusive"),
        )
        runtime_range = (
            declared.get("intelligence_minimum"),
            declared.get("intelligence_maximum_exclusive"),
        )
        compiler_supported = (
            compiler_range[0] in {PACK_COMPILER_VERSION, STABLE_PACK_COMPILER_VERSION}
            and compiler_range[1] == PACK_COMPILER_NEXT_BREAKING_VERSION
        )
        if not compiler_supported:
            diagnostic = PackDiagnosticV1(
                severity="error",
                code="unsupported_compiler_range",
                path="manifest.compatibility",
                message="v1 requires a compiler minimum of v1alpha1 or v1 and an exclusive v2 ceiling",
            )
            return PackCompatibilityResultV1(
                manifest_contract=manifest_contract,
                compiler_contract=STABLE_PACK_COMPILER_VERSION,
                intelligence_contract=STABLE_INTELLIGENCE_RUNTIME_VERSION,
                declared_compatibility_digest=declared_digest,
                status=PackCompatibilityStatus.REJECTED,
                diagnostics=(diagnostic,),
            )
        runtime_supported = (
            runtime_range[0] in {INTELLIGENCE_RUNTIME_VERSION, STABLE_INTELLIGENCE_RUNTIME_VERSION}
            and runtime_range[1] == INTELLIGENCE_RUNTIME_NEXT_BREAKING_VERSION
        )
        if not runtime_supported:
            diagnostic = PackDiagnosticV1(
                severity="error",
                code="unsupported_runtime_range",
                path="manifest.compatibility",
                message="v1 requires a runtime minimum of v1alpha1 or v1 and an exclusive v2 ceiling",
            )
            return PackCompatibilityResultV1(
                manifest_contract=manifest_contract,
                compiler_contract=STABLE_PACK_COMPILER_VERSION,
                intelligence_contract=STABLE_INTELLIGENCE_RUNTIME_VERSION,
                declared_compatibility_digest=declared_digest,
                status=PackCompatibilityStatus.REJECTED,
                diagnostics=(diagnostic,),
            )
        return PackCompatibilityResultV1(
            manifest_contract=manifest_contract,
            compiler_contract=STABLE_PACK_COMPILER_VERSION,
            intelligence_contract=STABLE_INTELLIGENCE_RUNTIME_VERSION,
            declared_compatibility_digest=declared_digest,
            status=PackCompatibilityStatus.SUPPORTED,
        )

    is_v1_prerelease = isinstance(manifest_contract, str) and manifest_contract.startswith(
        "ace.intelligence.domain-pack-manifest/v1"
    )
    status = PackCompatibilityStatus.MIGRATION_REQUIRED if is_v1_prerelease else PackCompatibilityStatus.REJECTED
    code = "manifest_migration_required" if is_v1_prerelease else "unsupported_manifest_contract"
    message = (
        "this prerelease manifest must be migrated offline to the stable v1 schema"
        if is_v1_prerelease
        else "the host accepts only the stable v1 contract and the documented v1alpha1 prior window"
    )
    diagnostic = PackDiagnosticV1(severity="error", code=code, path="manifest.contract", message=message)
    return PackCompatibilityResultV1(
        manifest_contract=normalized_manifest_contract,
        compiler_contract=STABLE_PACK_COMPILER_VERSION,
        intelligence_contract=STABLE_INTELLIGENCE_RUNTIME_VERSION,
        status=status,
        diagnostics=(diagnostic,),
    )


_FORBIDDEN_AUTHORITY_TOKENS = {
    "action",
    "command",
    "connector",
    "delivery",
    "execute",
    "extension",
    "network",
    "persist",
    "publish",
    "schedule",
}


def _validate_stable_authority_boundary(manifest: DomainPackManifestV1) -> None:
    if manifest.contract != DOMAIN_PACK_MANIFEST_STABLE_VERSION:
        return
    for request in manifest.authority_requests:
        parts = set(request.authority.replace("-", "_").split("_"))
        if parts & _FORBIDDEN_AUTHORITY_TOKENS:
            _fail(
                "authority_escalation",
                f"manifest.authority_requests.{request.request_id}.authority",
                "Domain Packs cannot request executable, transport, persistence, scheduling, delivery, publication, or action authority",
                stable=True,
            )
    for requirement in manifest.capability_requirements:
        parts = set(requirement.capability.replace("-", "_").split("_"))
        if parts & _FORBIDDEN_AUTHORITY_TOKENS:
            _fail(
                "capability_escalation",
                f"manifest.capability_requirements.{requirement.requirement_id}.capability",
                "Domain Packs cannot acquire connector, extension, transport, persistence, scheduling, delivery, publication, or action capability",
                stable=True,
            )


def _validate_stable_resource_boundaries(
    manifest: DomainPackManifestV1,
    modules: list[CompiledModuleV1],
) -> None:
    if manifest.contract != DOMAIN_PACK_MANIFEST_STABLE_VERSION:
        return
    for compiled in modules:
        if compiled.contract != SOURCE_MAPPING_MODULE_VERSION:
            continue
        module = SourceMappingModuleV1.model_validate_json(compiled.canonical_payload)
        for mapping in module.mappings:
            if "://" in mapping.source_definition_ref:
                _fail(
                    "network_location_forbidden",
                    f"modules.{compiled.module_id}.mappings.{mapping.mapping_id}.source_definition_ref",
                    "Domain Packs may name reviewed source definitions and URI schemes but cannot embed network locations",
                    stable=True,
                )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _reject_lone_surrogates(value: Any, *, path: str) -> None:
    pending: list[tuple[Any, str]] = [(value, path)]
    while pending:
        current, current_path = pending.pop()
        if isinstance(current, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                _fail(
                    "invalid_unicode_scalar",
                    current_path,
                    "JSON strings must contain Unicode scalar values",
                )
        elif isinstance(current, dict):
            for key, child in current.items():
                if any(0xD800 <= ord(character) <= 0xDFFF for character in key):
                    _fail(
                        "invalid_unicode_scalar",
                        current_path,
                        "JSON object keys must contain Unicode scalar values",
                    )
                pending.append((child, f"{current_path}.{key}"))
        elif isinstance(current, list):
            pending.extend((child, f"{current_path}.{index}") for index, child in enumerate(current))


def _parse_json(resource: bytes, *, path: str) -> Any:
    try:
        text = resource.decode("utf-8")
    except UnicodeDecodeError:
        _fail("invalid_utf8", path, "resource must be UTF-8 JSON")
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        _fail("invalid_json", path, str(exc))
    _reject_lone_surrogates(parsed, path=path)
    return parsed


def _compile_ontology(payload: Any, *, module_id: str, path: str) -> OntologyModuleV1:
    try:
        module = OntologyModuleV1.model_validate(payload)
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        diagnostic_path = f"{path}.{location}" if location else path
        _fail("invalid_module", diagnostic_path, error["msg"])
    if module.module_id != module_id:
        _fail("module_id_mismatch", f"{path}.module_id", "payload module_id must match its manifest reference")
    return module


def _compile_detection(payload: Any, *, module_id: str, path: str) -> DetectionModuleV1:
    try:
        module = DetectionModuleV1.model_validate(payload)
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        diagnostic_path = f"{path}.{location}" if location else path
        _fail("invalid_module", diagnostic_path, error["msg"])
    if module.module_id != module_id:
        _fail("module_id_mismatch", f"{path}.module_id", "payload module_id must match its manifest reference")
    return module


def _compile_typed_module(payload: Any, *, module_id: str, path: str, model):
    try:
        module = model.model_validate(payload)
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        diagnostic_path = f"{path}.{location}" if location else path
        _fail("invalid_module", diagnostic_path, error["msg"])
    except (RecursionError, TypeError, UnicodeError, ValueError):
        _fail(
            "invalid_module",
            path,
            "module validation failed within the closed contract bounds",
        )
    if module.module_id != module_id:
        _fail("module_id_mismatch", f"{path}.module_id", "payload module_id must match its manifest reference")
    return module


def _compile_detection_v1alpha2(
    payload: Any,
    *,
    module_id: str,
    path: str,
) -> DetectionModuleV1Alpha2:
    return _compile_typed_module(
        payload,
        module_id=module_id,
        path=path,
        model=DetectionModuleV1Alpha2,
    )


def _compile_detection_v1alpha3(
    payload: Any,
    *,
    module_id: str,
    path: str,
) -> DetectionModuleV1Alpha3:
    return _compile_typed_module(
        payload,
        module_id=module_id,
        path=path,
        model=DetectionModuleV1Alpha3,
    )


def _compile_personas(payload: Any, *, module_id: str, path: str) -> PersonasModuleV1:
    return _compile_typed_module(payload, module_id=module_id, path=path, model=PersonasModuleV1)


def _compile_decision_outcomes(
    payload: Any,
    *,
    module_id: str,
    path: str,
) -> DecisionOutcomesModuleV1:
    return _compile_typed_module(
        payload,
        module_id=module_id,
        path=path,
        model=DecisionOutcomesModuleV1,
    )


def _compile_synthesis(payload: Any, *, module_id: str, path: str) -> SynthesisModuleV1:
    return _compile_typed_module(payload, module_id=module_id, path=path, model=SynthesisModuleV1)


def _compile_synthesis_v1alpha2(
    payload: Any,
    *,
    module_id: str,
    path: str,
) -> SynthesisModuleV1Alpha2:
    return _compile_typed_module(
        payload,
        module_id=module_id,
        path=path,
        model=SynthesisModuleV1Alpha2,
    )


def _compile_orientation(payload: Any, *, module_id: str, path: str) -> OrientationModuleV1:
    return _compile_typed_module(payload, module_id=module_id, path=path, model=OrientationModuleV1)


def _compile_epistemic_status(
    payload: Any,
    *,
    module_id: str,
    path: str,
) -> EpistemicStatusModuleV1:
    return _compile_typed_module(
        payload,
        module_id=module_id,
        path=path,
        model=EpistemicStatusModuleV1,
    )


def _compile_epistemic_status_v1alpha2(
    payload: Any,
    *,
    module_id: str,
    path: str,
) -> EpistemicStatusModuleV1Alpha2:
    return _compile_typed_module(
        payload,
        module_id=module_id,
        path=path,
        model=EpistemicStatusModuleV1Alpha2,
    )


_UNSAFE_DECLARATIVE_KEYS = {
    "args",
    "callback",
    "callbacks",
    "callable",
    "class",
    "code",
    "command",
    "condition",
    "conditions",
    "eval",
    "exec",
    "executable",
    "expression",
    "expressions",
    "function",
    "handler",
    "import",
    "jmespath",
    "jsonpath",
    "kwargs",
    "loop",
    "loops",
    "operation",
    "operations",
    "operator",
    "plugin",
    "predicate",
    "predicates",
    "python",
    "regex",
    "script",
    "template",
    "templates",
}
_PROTECTED_OUTPUT_KEYS = {
    "acquisition_mode",
    "acquisition_receipt_digest",
    "acquisition_receipt_ref",
    "activation",
    "activation_id",
    "activation_revision",
    "as_of",
    "entity_ref",
    "event_effective_at",
    "ingested_at",
    "mode",
    "observed_at",
    "product_id",
    "projected_at",
    "source_digest",
    "source_published_at",
    "source_ref",
    "source_snapshot_digest",
    "source_snapshot_ref",
}


def _reject_executable_mapping_shape(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.casefold().replace("-", "_")
            child_path = f"{path}.{key}"
            if normalized in _UNSAFE_DECLARATIVE_KEYS or any(
                normalized.endswith(suffix)
                for suffix in ("_callback", "_code", "_expression", "_predicate", "_regex", "_template")
            ):
                _fail(
                    "unsafe_executable_field",
                    child_path,
                    "source mappings cannot contain expressions, programs, callbacks, templates, or operations",
                )
            if normalized in _PROTECTED_OUTPUT_KEYS:
                _fail(
                    "protected_mapping_field",
                    child_path,
                    "source mappings cannot select or override host-owned envelope fields",
                )
            _reject_executable_mapping_shape(child, path=child_path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_executable_mapping_shape(child, path=f"{path}.{index}")


def _compile_source_mapping(payload: Any, *, module_id: str, path: str) -> SourceMappingModuleV1:
    try:
        _reject_executable_mapping_shape(payload, path=path)
    except RecursionError:
        _fail(
            "mapping_too_deep",
            path,
            "source mapping exceeds the bounded nesting depth",
        )
    return _compile_typed_module(payload, module_id=module_id, path=path, model=SourceMappingModuleV1)


_MODULE_VALIDATORS: dict[str, Callable[..., Any]] = {
    ONTOLOGY_MODULE_VERSION: _compile_ontology,
    DETECTION_MODULE_VERSION: _compile_detection,
    DETECTION_MODULE_V1ALPHA2_VERSION: _compile_detection_v1alpha2,
    DETECTION_MODULE_V1ALPHA3_VERSION: _compile_detection_v1alpha3,
    DECISION_OUTCOMES_MODULE_VERSION: _compile_decision_outcomes,
    PERSONAS_MODULE_VERSION: _compile_personas,
    SOURCE_MAPPING_MODULE_VERSION: _compile_source_mapping,
    ORIENTATION_MODULE_VERSION: _compile_orientation,
    SYNTHESIS_MODULE_VERSION: _compile_synthesis,
    SYNTHESIS_MODULE_V1ALPHA2_VERSION: _compile_synthesis_v1alpha2,
    EPISTEMIC_STATUS_MODULE_VERSION: _compile_epistemic_status,
    EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION: _compile_epistemic_status_v1alpha2,
}


def _validate_source_mapping_modules(
    manifest: DomainPackManifestV1,
    modules: list[CompiledModuleV1],
) -> None:
    ontologies = {
        item.module_id: OntologyModuleV1.model_validate_json(item.canonical_payload)
        for item in modules
        if item.contract == ONTOLOGY_MODULE_VERSION
    }
    entity_owner: dict[str, str] = {}
    entity_by_id = {}
    for module_id, ontology in ontologies.items():
        for entity in ontology.entity_types:
            entity_owner[entity.entity_type_id] = module_id
            entity_by_id[entity.entity_type_id] = entity

    requirement_ids = {item.requirement_id for item in manifest.capability_requirements}
    authority_ids = {item.request_id for item in manifest.authority_requests}
    mapping_owner: dict[str, str] = {}
    for compiled in modules:
        if compiled.contract != SOURCE_MAPPING_MODULE_VERSION:
            continue
        module = SourceMappingModuleV1.model_validate_json(compiled.canonical_payload)
        direct_ontology_dependencies = set(compiled.depends_on) & set(ontologies)
        if not direct_ontology_dependencies:
            _fail(
                "missing_ontology_dependency",
                f"modules.{compiled.module_id}.depends_on",
                "a source-mapping module must directly depend on an ontology module",
            )
        for mapping in module.mappings:
            mapping_path = f"modules.{compiled.module_id}.mappings.{mapping.mapping_id}"
            owner = mapping_owner.get(mapping.mapping_id)
            if owner is not None:
                _fail(
                    "duplicate_mapping_id",
                    f"{mapping_path}.mapping_id",
                    f"mapping ID is already declared by module {owner}",
                )
            mapping_owner[mapping.mapping_id] = compiled.module_id
            if mapping.capability_requirement_id not in requirement_ids:
                _fail(
                    "unknown_capability_requirement",
                    f"{mapping_path}.capability_requirement_id",
                    "mapping references an undeclared manifest capability requirement",
                )
            if mapping.authority_request_id not in authority_ids:
                _fail(
                    "unknown_authority_request",
                    f"{mapping_path}.authority_request_id",
                    "mapping references an undeclared manifest authority request",
                )
            ontology_owner = entity_owner.get(mapping.entity_type_id)
            if ontology_owner is None:
                _fail(
                    "unknown_target_entity_type",
                    f"{mapping_path}.entity_type_id",
                    "mapping references an unknown ontology entity type",
                )
            if ontology_owner not in direct_ontology_dependencies:
                _fail(
                    "entity_type_outside_dependency",
                    f"{mapping_path}.entity_type_id",
                    "target entity type is outside the mapping module's direct ontology dependencies",
                )
            entity = entity_by_id[mapping.entity_type_id]
            attributes = {item.attribute_id: item for item in entity.attributes}
            mapped_ids = {item.attribute_id for item in mapping.attribute_mappings}
            for attribute_mapping in mapping.attribute_mappings:
                if attribute_mapping.attribute_id not in attributes:
                    attribute_path = f"{mapping_path}.attribute_mappings.{attribute_mapping.attribute_id}"
                    _fail(
                        "unknown_target_attribute",
                        f"{attribute_path}.attribute_id",
                        "mapping references an unknown target attribute",
                    )
            missing_required = sorted(
                item.attribute_id for item in entity.attributes if item.required and item.attribute_id not in mapped_ids
            )
            if missing_required:
                _fail(
                    "missing_required_outputs",
                    f"{mapping_path}.attribute_mappings",
                    f"required target attributes must be mapped exactly once: {missing_required}",
                )
            for attribute_mapping in mapping.attribute_mappings:
                attribute_path = f"{mapping_path}.attribute_mappings.{attribute_mapping.attribute_id}"
                target = attributes[attribute_mapping.attribute_id]
                if attribute_mapping.transform is SourceMappingTransform.DECIMAL_TEXT_TO_NUMBER:
                    if target.value_type is not AttributeValueType.NUMBER or target.many:
                        _fail(
                            "incompatible_transform_output",
                            f"{attribute_path}.transform",
                            "decimal_text_to_number requires one number-valued target attribute",
                        )
                has_string_constraints = any(
                    value is not None
                    for value in (
                        attribute_mapping.min_length,
                        attribute_mapping.max_length,
                        attribute_mapping.character_set,
                    )
                )
                if (
                    has_string_constraints
                    and attribute_mapping.transform is SourceMappingTransform.COPY
                    and target.value_type
                    not in {
                        AttributeValueType.STRING,
                        AttributeValueType.DATETIME,
                        AttributeValueType.ENTITY_REF,
                    }
                ):
                    _fail(
                        "incompatible_string_constraints",
                        attribute_path,
                        "string constraints require a copied string-like target or decimal text input",
                    )
                if attribute_mapping.character_set is not None and (
                    attribute_mapping.transform is not SourceMappingTransform.COPY
                    or target.value_type is not AttributeValueType.STRING
                ):
                    _fail(
                        "incompatible_character_set",
                        f"{attribute_path}.character_set",
                        "character_set is supported only for copied string attributes",
                    )


def _validate_orientation_modules(modules: list[CompiledModuleV1]) -> None:
    """Every orientation policy must name one exact declared template and persona set."""

    template_counts: dict[str, int] = {}
    persona_counts: dict[str, int] = {}
    synthesis_models = {
        SYNTHESIS_MODULE_VERSION: SynthesisModuleV1,
        SYNTHESIS_MODULE_V1ALPHA2_VERSION: SynthesisModuleV1Alpha2,
    }
    for compiled in modules:
        model = synthesis_models.get(compiled.contract)
        if model is not None:
            module = model.model_validate_json(compiled.canonical_payload)
            for template in module.brief_templates:
                template_counts[template.template_id] = template_counts.get(template.template_id, 0) + 1
        if compiled.contract == PERSONAS_MODULE_VERSION:
            module = PersonasModuleV1.model_validate_json(compiled.canonical_payload)
            for persona in module.personas:
                persona_counts[persona.persona_id] = persona_counts.get(persona.persona_id, 0) + 1
        if compiled.contract == ORIENTATION_MODULE_VERSION:
            module = OrientationModuleV1.model_validate_json(compiled.canonical_payload)
            for persona in module.personas:
                persona_counts[persona.persona_id] = persona_counts.get(persona.persona_id, 0) + 1

    policy_owner: dict[str, str] = {}
    for compiled in modules:
        if compiled.contract != ORIENTATION_MODULE_VERSION:
            continue
        module = OrientationModuleV1.model_validate_json(compiled.canonical_payload)
        for policy in module.initial_orientation_policies:
            policy_path = f"modules.{compiled.module_id}.initial_orientation_policies.{policy.policy_id}"
            owner = policy_owner.get(policy.policy_id)
            if owner is not None:
                _fail(
                    "duplicate_orientation_policy_id",
                    f"{policy_path}.policy_id",
                    f"initial orientation policy ID is already declared by module {owner}",
                )
            policy_owner[policy.policy_id] = compiled.module_id
            if template_counts.get(policy.brief_template_id, 0) != 1:
                _fail(
                    "unresolved_orientation_template",
                    f"{policy_path}.brief_template_id",
                    "orientation policy must name a Brief template declared exactly once in this pack",
                )
            unresolved = sorted(item for item in policy.persona_ids if persona_counts.get(item, 0) != 1)
            if unresolved:
                _fail(
                    "unresolved_orientation_personas",
                    f"{policy_path}.persona_ids",
                    f"orientation policy personas must each be declared exactly once in this pack: {unresolved}",
                )


def _validate_dependency_graph(manifest: DomainPackManifestV1) -> None:
    dependencies = {item.module_id: item.depends_on for item in manifest.modules}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module_id: str) -> None:
        if module_id in visiting:
            _fail("module_cycle", f"modules.{module_id}.depends_on", "module dependency graph contains a cycle")
        if module_id in visited:
            return
        visiting.add(module_id)
        for dependency in dependencies[module_id]:
            visit(dependency)
        visiting.remove(module_id)
        visited.add(module_id)

    for module_id in sorted(dependencies):
        visit(module_id)


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _compile_pack(
    manifest: DomainPackManifestV1,
    resources: Mapping[str, bytes],
) -> CompiledDomainPackV1:
    """Compile exact in-memory JSON resources into canonical, content-addressed Pack IR.

    The function performs no discovery, import, I/O, clock read, model call, secret lookup,
    registry mutation, or persistence operation.
    """

    compatibility = negotiate_pack_compatibility(
        manifest.contract,
        manifest.compatibility.model_dump(mode="python"),
    )
    if compatibility.status not in {PackCompatibilityStatus.SUPPORTED, PackCompatibilityStatus.DEPRECATED}:
        diagnostic = compatibility.diagnostics[0]
        _fail(diagnostic.code, diagnostic.path, diagnostic.message, stable=True)
    _validate_stable_authority_boundary(manifest)

    declared_paths = {item.path for item in manifest.resources}
    supplied_paths = set(resources)
    if supplied_paths != declared_paths:
        missing = sorted(declared_paths - supplied_paths)
        extra = sorted(supplied_paths - declared_paths)
        _fail("resource_set_mismatch", "resources", f"missing={missing}; undeclared={extra}")

    resource_by_id = {item.resource_id: item for item in manifest.resources}
    total_bytes = 0
    for resource in manifest.resources:
        payload = resources[resource.path]
        if not isinstance(payload, bytes):
            _fail("invalid_resource_type", f"resources.{resource.resource_id}", "resource payload must be bytes")
        total_bytes += len(payload)
        if len(payload) > MAX_RESOURCE_BYTES:
            _fail(
                "resource_too_large",
                f"resources.{resource.resource_id}",
                f"resource exceeds the {MAX_RESOURCE_BYTES}-byte bound",
            )
        if _sha256_bytes(payload) != resource.digest:
            _fail("digest_mismatch", f"resources.{resource.resource_id}.digest", "resource digest does not match bytes")
    if total_bytes > MAX_PACK_BYTES:
        _fail("pack_too_large", "resources", f"resources exceed the {MAX_PACK_BYTES}-byte pack bound")

    _validate_dependency_graph(manifest)
    compiled_modules: list[CompiledModuleV1] = []
    for module_ref in manifest.modules:
        validator = _MODULE_VALIDATORS.get(module_ref.contract)
        if validator is None:
            _fail("unknown_module_contract", f"modules.{module_ref.module_id}.contract", module_ref.contract)
        resource = resource_by_id[module_ref.resource_id]
        payload = _parse_json(resources[resource.path], path=f"resources.{resource.resource_id}")
        module = validator(payload, module_id=module_ref.module_id, path=f"modules.{module_ref.module_id}")
        try:
            canonical_payload = canonical_json(module)
            module_digest = f"sha256:{canonical_hash(module)}"
        except (RecursionError, UnicodeError, ValueError) as exc:
            _fail(
                "invalid_module_material",
                f"modules.{module_ref.module_id}",
                str(exc),
            )
        compiled_modules.append(
            CompiledModuleV1(
                module_id=module_ref.module_id,
                contract=module_ref.contract,
                depends_on=module_ref.depends_on,
                canonical_payload=canonical_payload,
                module_digest=module_digest,
            )
        )

    _validate_source_mapping_modules(manifest, compiled_modules)
    _validate_orientation_modules(compiled_modules)
    _validate_stable_resource_boundaries(manifest, compiled_modules)

    try:
        return CompiledDomainPackV1(
            contract=(
                COMPILED_DOMAIN_PACK_STABLE_VERSION
                if manifest.contract == DOMAIN_PACK_MANIFEST_STABLE_VERSION
                else "ace.intelligence.compiled-domain-pack/v1alpha1"
            ),
            compiler_contract=compatibility.compiler_contract,
            intelligence_contract=compatibility.intelligence_contract,
            manifest_contract=manifest.contract,
            declared_compatibility=(
                manifest.compatibility if manifest.contract == DOMAIN_PACK_MANIFEST_STABLE_VERSION else None
            ),
            metadata=manifest.metadata,
            modules=tuple(sorted(compiled_modules, key=lambda item: item.module_id)),
            capability_requirements=manifest.capability_requirements,
            authority_requests=manifest.authority_requests,
            overlay_slots=manifest.overlay_slots,
        )
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        path = f"pack_ir.{location}" if location else "pack_ir"
        _fail("invalid_pack_ir", path, error["msg"])


def compile_pack(
    manifest: DomainPackManifestV1,
    resources: Mapping[str, bytes],
) -> CompiledDomainPackV1:
    """Compile exact resources while selecting diagnostics from the declared manifest contract."""

    token = _STABLE_DIAGNOSTICS.set(manifest.contract == DOMAIN_PACK_MANIFEST_STABLE_VERSION)
    try:
        return _compile_pack(manifest, resources)
    finally:
        _STABLE_DIAGNOSTICS.reset(token)


def compile_pack_document(
    manifest_document: bytes,
    resources: Mapping[str, bytes],
) -> CompiledDomainPackV1:
    """Validate an untrusted JSON manifest and compile its exact in-memory resources."""

    if not isinstance(manifest_document, bytes):
        _fail("invalid_manifest_type", "manifest", "manifest document must be bytes")
    if len(manifest_document) > MAX_RESOURCE_BYTES:
        _fail("manifest_too_large", "manifest", f"manifest exceeds the {MAX_RESOURCE_BYTES}-byte bound")
    payload = _parse_json(manifest_document, path="manifest")
    if not isinstance(payload, dict):
        _fail("invalid_manifest", "manifest", "manifest must be a JSON object", stable=True)
    manifest_contract = payload.get("contract")
    if not isinstance(manifest_contract, str):
        _fail("invalid_manifest_contract", "manifest.contract", "manifest contract must be a string", stable=True)
    compatibility = negotiate_pack_compatibility(manifest_contract, payload.get("compatibility"))
    if compatibility.status not in {PackCompatibilityStatus.SUPPORTED, PackCompatibilityStatus.DEPRECATED}:
        diagnostic = compatibility.diagnostics[0]
        _fail(diagnostic.code, diagnostic.path, diagnostic.message, stable=True)
    try:
        manifest = DomainPackManifestV1.model_validate(payload)
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        path = f"manifest.{location}" if location else "manifest"
        _fail("invalid_manifest", path, error["msg"], stable=manifest_contract == DOMAIN_PACK_MANIFEST_STABLE_VERSION)
    return compile_pack(manifest, resources)


def compile_pack_document_with_report(
    manifest_document: bytes,
    resources: Mapping[str, bytes],
) -> CompiledPackResultV1:
    """Compile and return exact successful negotiation and compilation evidence."""

    pack = compile_pack_document(manifest_document, resources)
    compatibility = negotiate_pack_compatibility(
        pack.manifest_contract,
        pack.declared_compatibility.model_dump(mode="python") if pack.declared_compatibility is not None else None,
    )
    compilation = StablePackCompilationResultV1(
        manifest_contract=pack.manifest_contract,
        compiler_contract=pack.compiler_contract,
        intelligence_contract=pack.intelligence_contract,
        compatibility_result_id=compatibility.result_id,
        compatibility_result_digest=compatibility.result_digest,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
        diagnostics=compatibility.diagnostics,
    )
    return CompiledPackResultV1(pack=pack, compatibility=compatibility, compilation=compilation)


def validate_compiled_pack_set(
    packs: tuple[CompiledDomainPackV1, ...] | list[CompiledDomainPackV1],
) -> tuple[CompiledDomainPackV1, ...]:
    """Validate deterministic co-installation without creating mutable registry state."""

    validated: list[CompiledDomainPackV1] = []
    by_id: dict[str, CompiledDomainPackV1] = {}
    for candidate in packs:
        try:
            pack = CompiledDomainPackV1.model_validate(candidate.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError):
            _fail("invalid_pack_ir", "packs", "co-installed Pack IR failed exact revalidation", stable=True)
        prior = by_id.get(pack.metadata.pack_id)
        if prior is not None:
            _fail(
                "pack_identifier_collision",
                f"packs.{pack.metadata.pack_id}",
                "co-installed Domain Packs must use globally unique pack_id values",
                stable=True,
            )
        by_id[pack.metadata.pack_id] = pack
        validated.append(pack)
    return tuple(sorted(validated, key=lambda item: item.metadata.pack_id))
