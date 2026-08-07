"""Pure, deterministic compiler for inert declarative Domain Packs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Callable

from pydantic import ValidationError

from ace.core.contracts import canonical_hash, canonical_json
from ace.intelligence.contracts.common import MAX_PACK_BYTES, MAX_RESOURCE_BYTES
from ace.intelligence.contracts.detection import (
    DETECTION_MODULE_V1ALPHA2_VERSION,
    DETECTION_MODULE_VERSION,
    DetectionModuleV1,
    DetectionModuleV1Alpha2,
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
from ace.intelligence.contracts.pack import (
    ONTOLOGY_MODULE_VERSION,
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
from ace.intelligence.packs.diagnostics import PackCompilationReportV1, PackDiagnosticV1


class PackCompilationError(ValueError):
    """A fail-closed compilation error with stable diagnostics."""

    def __init__(self, report: PackCompilationReportV1) -> None:
        self.report = report
        first = report.diagnostics[0]
        super().__init__(f"{first.code} at {first.path}: {first.message}")


def _fail(code: str, path: str, message: str) -> None:
    bounded_code = str(code)[:120] or "compilation_error"
    bounded_path = str(path)[:500] or "pack"
    bounded_message = str(message)[:1_000] or "pack compilation failed"
    raise PackCompilationError(
        PackCompilationReportV1(
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
    DECISION_OUTCOMES_MODULE_VERSION: _compile_decision_outcomes,
    PERSONAS_MODULE_VERSION: _compile_personas,
    SOURCE_MAPPING_MODULE_VERSION: _compile_source_mapping,
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


def compile_pack(
    manifest: DomainPackManifestV1,
    resources: Mapping[str, bytes],
) -> CompiledDomainPackV1:
    """Compile exact in-memory JSON resources into canonical, content-addressed Pack IR.

    The function performs no discovery, import, I/O, clock read, model call, secret lookup,
    registry mutation, or persistence operation.
    """

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

    try:
        return CompiledDomainPackV1(
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
    try:
        manifest = DomainPackManifestV1.model_validate(payload)
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        path = f"manifest.{location}" if location else "manifest"
        _fail("invalid_manifest", path, error["msg"])
    return compile_pack(manifest, resources)
