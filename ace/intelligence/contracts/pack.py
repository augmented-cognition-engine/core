"""Strict declarative Domain Pack and ontology-module contracts."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, StrictBool, StrictFloat, StrictInt, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.intelligence.contracts.common import (
    MAX_DECLARATIONS,
    normalized_strings,
    parse_json_strict,
    sorted_unique,
    validate_contract,
    validate_digest,
    validate_resource_path,
    validate_slug,
    validate_version,
)
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

DOMAIN_PACK_MANIFEST_VERSION = "ace.intelligence.domain-pack-manifest/v1alpha1"
DOMAIN_PACK_MANIFEST_STABLE_VERSION = "ace.intelligence.domain-pack-manifest/v1"
ONTOLOGY_MODULE_VERSION = "ace.intelligence.ontology/v1alpha1"
COMPILED_DOMAIN_PACK_VERSION = "ace.intelligence.compiled-domain-pack/v1alpha1"
COMPILED_DOMAIN_PACK_STABLE_VERSION = "ace.intelligence.compiled-domain-pack/v1"
PACK_COMPILER_VERSION = "ace.intelligence.pack-compiler/v1alpha1"
INTELLIGENCE_RUNTIME_VERSION = "ace.intelligence.runtime/v1alpha1"
STABLE_PACK_COMPILER_VERSION = "ace.intelligence.pack-compiler/v1"
STABLE_INTELLIGENCE_RUNTIME_VERSION = "ace.intelligence.runtime/v1"
PACK_COMPILER_NEXT_BREAKING_VERSION = "ace.intelligence.pack-compiler/v2"
INTELLIGENCE_RUNTIME_NEXT_BREAKING_VERSION = "ace.intelligence.runtime/v2"


class AttributeValueType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    ENTITY_REF = "entity_ref"
    JSON = "json"


class OverlayValueKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    STRING_LIST = "string_list"
    JSON = "json"


def _matches_overlay_kind(value: Any, kind: OverlayValueKind) -> bool:
    if kind is OverlayValueKind.STRING:
        return isinstance(value, str)
    if kind is OverlayValueKind.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if kind is OverlayValueKind.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if kind is OverlayValueKind.BOOLEAN:
        return isinstance(value, bool)
    if kind is OverlayValueKind.STRING_LIST:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return kind is OverlayValueKind.JSON


class PackMetadataV1(FrozenContract):
    pack_id: str
    version: str
    display_name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1_000)

    @field_validator("pack_id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        return validate_slug(value, name="pack_id")

    @field_validator("version")
    @classmethod
    def validate_pack_version(cls, value: str) -> str:
        return validate_version(value)


class PackCompatibilityV1(FrozenContract):
    compiler_contract: Literal["ace.intelligence.pack-compiler/v1alpha1"] = PACK_COMPILER_VERSION
    intelligence_contract: Literal["ace.intelligence.runtime/v1alpha1"] = INTELLIGENCE_RUNTIME_VERSION


class PackCompatibilityRangeV1(FrozenContract):
    """Closed compatibility window declared by the stable manifest contract."""

    compiler_minimum: Literal[
        "ace.intelligence.pack-compiler/v1alpha1",
        "ace.intelligence.pack-compiler/v1",
    ] = PACK_COMPILER_VERSION
    compiler_maximum_exclusive: Literal["ace.intelligence.pack-compiler/v2"] = (
        PACK_COMPILER_NEXT_BREAKING_VERSION
    )
    intelligence_minimum: Literal[
        "ace.intelligence.runtime/v1alpha1",
        "ace.intelligence.runtime/v1",
    ] = INTELLIGENCE_RUNTIME_VERSION
    intelligence_maximum_exclusive: Literal["ace.intelligence.runtime/v2"] = (
        INTELLIGENCE_RUNTIME_NEXT_BREAKING_VERSION
    )


class PackResourceV1(FrozenContract):
    resource_id: str
    path: str
    media_type: Literal["application/json"] = "application/json"
    digest: str

    @field_validator("resource_id")
    @classmethod
    def validate_resource_id(cls, value: str) -> str:
        return validate_slug(value, name="resource_id")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_resource_path(value)

    @field_validator("digest")
    @classmethod
    def validate_resource_digest(cls, value: str) -> str:
        return validate_digest(value)


class PackModuleRefV1(FrozenContract):
    module_id: str
    contract: str
    resource_id: str
    depends_on: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)

    @field_validator("module_id", "resource_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("contract")
    @classmethod
    def validate_module_contract(cls, value: str) -> str:
        return validate_contract(value)

    @field_validator("depends_on", mode="before")
    @classmethod
    def normalize_dependencies(cls, value: Any) -> tuple[str, ...]:
        result = normalized_strings(value, label="module dependencies")
        return tuple(validate_slug(item, name="module dependency") for item in result)

    @model_validator(mode="after")
    def reject_self_dependency(self) -> Self:
        if self.module_id in self.depends_on:
            raise ValueError("module cannot depend on itself")
        return self


class CapabilityRequirementV1(FrozenContract):
    requirement_id: str
    capability: str
    contract: str

    @field_validator("requirement_id", "capability")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("contract")
    @classmethod
    def validate_capability_contract(cls, value: str) -> str:
        return validate_contract(value)


class AuthorityRequestV1(FrozenContract):
    request_id: str
    authority: str

    @field_validator("request_id", "authority")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)


class OverlaySlotDeclarationV1(FrozenContract):
    slot_id: str
    value_kind: OverlayValueKind
    required: StrictBool = False
    minimum: StrictInt | StrictFloat | None = None
    maximum: StrictInt | StrictFloat | None = None
    min_items: StrictInt | None = None
    max_items: StrictInt | None = None
    allowed_values_json: tuple[str, ...] = Field(default_factory=tuple, max_length=64)

    @field_validator("slot_id")
    @classmethod
    def validate_slot_id(cls, value: str) -> str:
        return validate_slug(value, name="slot_id")

    @field_validator("min_items", "max_items")
    @classmethod
    def validate_item_bound(cls, value: int | None, info) -> int | None:
        if value is not None and not 0 <= value <= MAX_DECLARATIONS:
            raise ValueError(f"{info.field_name} must be between 0 and {MAX_DECLARATIONS}")
        return value

    @field_validator("allowed_values_json", mode="before")
    @classmethod
    def normalize_allowed_values(cls, value: Any) -> tuple[str, ...]:
        raw_values = normalized_strings(value, label="allowed overlay values", maximum=64)
        normalized: list[str] = []
        for raw in raw_values:
            try:
                normalized.append(canonical_json(parse_json_strict(raw)))
            except (TypeError, ValueError, RecursionError) as exc:
                raise ValueError("allowed overlay values must be valid finite JSON") from exc
        return tuple(sorted(set(normalized)))

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        has_numeric_bounds = self.minimum is not None or self.maximum is not None
        has_list_bounds = self.min_items is not None or self.max_items is not None
        if has_numeric_bounds and self.value_kind not in {OverlayValueKind.INTEGER, OverlayValueKind.NUMBER}:
            raise ValueError("numeric bounds require an integer or number overlay slot")
        if has_list_bounds and self.value_kind is not OverlayValueKind.STRING_LIST:
            raise ValueError("item bounds require a string_list overlay slot")
        if self.value_kind is OverlayValueKind.INTEGER and any(
            value is not None and not isinstance(value, int) for value in (self.minimum, self.maximum)
        ):
            raise ValueError("integer overlay bounds must be integers")
        if any(value is not None and not math.isfinite(value) for value in (self.minimum, self.maximum)):
            raise ValueError("numeric overlay bounds must be finite")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        if self.min_items is not None and self.max_items is not None and self.min_items > self.max_items:
            raise ValueError("min_items cannot exceed max_items")
        if any(
            not _matches_overlay_kind(parse_json_strict(value), self.value_kind) for value in self.allowed_values_json
        ):
            raise ValueError("allowed overlay values must match the slot value kind")
        return self


class AttributeDeclarationV1(FrozenContract):
    attribute_id: str
    value_type: AttributeValueType
    required: StrictBool = False
    many: StrictBool = False

    @field_validator("attribute_id")
    @classmethod
    def validate_attribute_id(cls, value: str) -> str:
        return validate_slug(value, name="attribute_id")


class EntityTypeDeclarationV1(FrozenContract):
    entity_type_id: str
    display_name: str | None = Field(default=None, max_length=160)
    attributes: tuple[AttributeDeclarationV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)

    @field_validator("entity_type_id")
    @classmethod
    def validate_entity_type_id(cls, value: str) -> str:
        return validate_slug(value, name="entity_type_id")

    @field_validator("attributes")
    @classmethod
    def normalize_attributes(cls, value: tuple[AttributeDeclarationV1, ...]) -> tuple[AttributeDeclarationV1, ...]:
        return sorted_unique(value, key=lambda item: item.attribute_id, label="entity attributes")


class RelationTypeDeclarationV1(FrozenContract):
    relation_type_id: str
    source_entity_types: tuple[str, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    target_entity_types: tuple[str, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    attributes: tuple[AttributeDeclarationV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)

    @field_validator("relation_type_id")
    @classmethod
    def validate_relation_type_id(cls, value: str) -> str:
        return validate_slug(value, name="relation_type_id")

    @field_validator("source_entity_types", "target_entity_types", mode="before")
    @classmethod
    def normalize_endpoints(cls, value: Any, info) -> tuple[str, ...]:
        result = normalized_strings(value, label=info.field_name)
        return tuple(validate_slug(item, name=info.field_name) for item in result)

    @field_validator("attributes")
    @classmethod
    def normalize_attributes(cls, value: tuple[AttributeDeclarationV1, ...]) -> tuple[AttributeDeclarationV1, ...]:
        return sorted_unique(value, key=lambda item: item.attribute_id, label="relation attributes")


class OntologyModuleV1(FrozenContract):
    contract: Literal["ace.intelligence.ontology/v1alpha1"] = ONTOLOGY_MODULE_VERSION
    module_id: str
    entity_types: tuple[EntityTypeDeclarationV1, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    relation_types: tuple[RelationTypeDeclarationV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("entity_types")
    @classmethod
    def normalize_entities(cls, value: tuple[EntityTypeDeclarationV1, ...]) -> tuple[EntityTypeDeclarationV1, ...]:
        return sorted_unique(value, key=lambda item: item.entity_type_id, label="entity types")

    @field_validator("relation_types")
    @classmethod
    def normalize_relations(cls, value: tuple[RelationTypeDeclarationV1, ...]) -> tuple[RelationTypeDeclarationV1, ...]:
        return sorted_unique(value, key=lambda item: item.relation_type_id, label="relation types")


class DomainPackManifestV1(FrozenContract):
    contract: Literal[
        "ace.intelligence.domain-pack-manifest/v1alpha1",
        "ace.intelligence.domain-pack-manifest/v1",
    ] = DOMAIN_PACK_MANIFEST_VERSION
    metadata: PackMetadataV1
    compatibility: PackCompatibilityV1 | PackCompatibilityRangeV1 = Field(default_factory=PackCompatibilityV1)
    resources: tuple[PackResourceV1, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    modules: tuple[PackModuleRefV1, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    capability_requirements: tuple[CapabilityRequirementV1, ...] = Field(
        default_factory=tuple, max_length=MAX_DECLARATIONS
    )
    authority_requests: tuple[AuthorityRequestV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    overlay_slots: tuple[OverlaySlotDeclarationV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)

    @field_validator("resources")
    @classmethod
    def normalize_resources(cls, value: tuple[PackResourceV1, ...]) -> tuple[PackResourceV1, ...]:
        normalized = sorted_unique(value, key=lambda item: item.resource_id, label="resources")
        paths = [item.path for item in normalized]
        if len(paths) != len(set(paths)):
            raise ValueError("resources must use unique paths")
        return normalized

    @field_validator("modules")
    @classmethod
    def normalize_modules(cls, value: tuple[PackModuleRefV1, ...]) -> tuple[PackModuleRefV1, ...]:
        return sorted_unique(value, key=lambda item: item.module_id, label="modules")

    @field_validator("capability_requirements")
    @classmethod
    def normalize_capabilities(cls, value: tuple[CapabilityRequirementV1, ...]) -> tuple[CapabilityRequirementV1, ...]:
        return sorted_unique(value, key=lambda item: item.requirement_id, label="capability requirements")

    @field_validator("authority_requests")
    @classmethod
    def normalize_authorities(cls, value: tuple[AuthorityRequestV1, ...]) -> tuple[AuthorityRequestV1, ...]:
        return sorted_unique(value, key=lambda item: item.request_id, label="authority requests")

    @field_validator("overlay_slots")
    @classmethod
    def normalize_overlay_slots(
        cls, value: tuple[OverlaySlotDeclarationV1, ...]
    ) -> tuple[OverlaySlotDeclarationV1, ...]:
        return sorted_unique(value, key=lambda item: item.slot_id, label="overlay slots")

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if self.contract == DOMAIN_PACK_MANIFEST_VERSION and not isinstance(
            self.compatibility, PackCompatibilityV1
        ):
            raise ValueError("v1alpha1 manifests require exact v1alpha1 compiler and runtime contracts")
        if self.contract == DOMAIN_PACK_MANIFEST_STABLE_VERSION and not isinstance(
            self.compatibility, PackCompatibilityRangeV1
        ):
            raise ValueError("v1 manifests require explicit compiler and runtime compatibility ranges")
        resource_ids = {item.resource_id for item in self.resources}
        module_ids = {item.module_id for item in self.modules}
        referenced_resources = [item.resource_id for item in self.modules]
        missing_resources = set(referenced_resources) - resource_ids
        if missing_resources:
            raise ValueError(f"modules reference unknown resources: {sorted(missing_resources)}")
        if len(referenced_resources) != len(set(referenced_resources)):
            raise ValueError("one resource cannot back multiple modules")
        if set(referenced_resources) != resource_ids:
            raise ValueError("every declared resource must back exactly one module")
        unknown_dependencies = {dep for item in self.modules for dep in item.depends_on} - module_ids
        if unknown_dependencies:
            raise ValueError(f"modules reference unknown dependencies: {sorted(unknown_dependencies)}")
        return self


class StableDomainPackManifestV1(DomainPackManifestV1):
    """The distributed stable v1 manifest schema for third-party packs."""

    contract: Literal["ace.intelligence.domain-pack-manifest/v1"] = DOMAIN_PACK_MANIFEST_STABLE_VERSION
    compatibility: PackCompatibilityRangeV1 = Field(default_factory=PackCompatibilityRangeV1)


class CompiledModuleV1(FrozenContract):
    module_id: str
    contract: str
    depends_on: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    canonical_payload: str = Field(min_length=2, max_length=1_000_000)
    module_digest: str

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        return validate_slug(value, name="module_id")

    @field_validator("contract")
    @classmethod
    def validate_compiled_contract(cls, value: str) -> str:
        return validate_contract(value)

    @field_validator("depends_on", mode="before")
    @classmethod
    def normalize_dependencies(cls, value: Any) -> tuple[str, ...]:
        return tuple(
            validate_slug(item, name="module dependency")
            for item in normalized_strings(value, label="module dependencies")
        )

    @field_validator("module_digest")
    @classmethod
    def validate_module_digest(cls, value: str) -> str:
        return validate_digest(value)

    @model_validator(mode="after")
    def validate_compiled_payload(self) -> Self:
        try:
            payload = parse_json_strict(self.canonical_payload)
        except (ValueError, RecursionError) as exc:
            raise ValueError("compiled module payload must be valid JSON") from exc
        if canonical_json(payload) != self.canonical_payload:
            raise ValueError("compiled module payload must already be canonical JSON")
        model_by_contract = {
            ONTOLOGY_MODULE_VERSION: OntologyModuleV1,
            DETECTION_MODULE_VERSION: DetectionModuleV1,
            DETECTION_MODULE_V1ALPHA2_VERSION: DetectionModuleV1Alpha2,
            DECISION_OUTCOMES_MODULE_VERSION: DecisionOutcomesModuleV1,
            PERSONAS_MODULE_VERSION: PersonasModuleV1,
            SOURCE_MAPPING_MODULE_VERSION: SourceMappingModuleV1,
            SYNTHESIS_MODULE_VERSION: SynthesisModuleV1,
            SYNTHESIS_MODULE_V1ALPHA2_VERSION: SynthesisModuleV1Alpha2,
            EPISTEMIC_STATUS_MODULE_VERSION: EpistemicStatusModuleV1,
            EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION: EpistemicStatusModuleV1Alpha2,
        }
        model = model_by_contract.get(self.contract)
        if model is None:
            raise ValueError("compiled module contract is not supported by this compiler")
        module = model.model_validate(payload)
        if module.module_id != self.module_id:
            raise ValueError("compiled payload module_id must match the compiled module")
        if canonical_json(module) != self.canonical_payload:
            raise ValueError("compiled module payload must equal its typed canonical normalization")
        expected_digest = f"sha256:{canonical_hash(payload)}"
        if self.module_digest != expected_digest:
            raise ValueError("compiled module digest does not match its canonical payload")
        return self


def _validate_compiled_module_graph(
    modules: tuple[CompiledModuleV1, ...],
    capability_requirements: tuple[CapabilityRequirementV1, ...],
    authority_requests: tuple[AuthorityRequestV1, ...],
) -> None:
    module_ids = {item.module_id for item in modules}
    unknown_dependencies = {dep for item in modules for dep in item.depends_on} - module_ids
    if unknown_dependencies:
        raise ValueError(f"compiled modules reference unknown dependencies: {sorted(unknown_dependencies)}")

    module_by_id = {item.module_id: item for item in modules}
    visiting: set[str] = set()
    transitive_cache: dict[str, set[str]] = {}

    def transitive_dependencies(module_id: str) -> set[str]:
        if module_id in transitive_cache:
            return transitive_cache[module_id]
        if module_id in visiting:
            raise ValueError("compiled module dependency graph contains a cycle")
        visiting.add(module_id)
        result: set[str] = set()
        for dependency in module_by_id[module_id].depends_on:
            result.add(dependency)
            result.update(transitive_dependencies(dependency))
        visiting.remove(module_id)
        transitive_cache[module_id] = result
        return result

    ontologies = {
        item.module_id: OntologyModuleV1.model_validate_json(item.canonical_payload)
        for item in modules
        if item.contract == ONTOLOGY_MODULE_VERSION
    }
    detection_models = {
        DETECTION_MODULE_VERSION: DetectionModuleV1,
        DETECTION_MODULE_V1ALPHA2_VERSION: DetectionModuleV1Alpha2,
    }
    detections = {
        item.module_id: detection_models[item.contract].model_validate_json(item.canonical_payload)
        for item in modules
        if item.contract in detection_models
    }
    decision_outcome_modules = {
        item.module_id: DecisionOutcomesModuleV1.model_validate_json(item.canonical_payload)
        for item in modules
        if item.contract == DECISION_OUTCOMES_MODULE_VERSION
    }
    synthesis_models = {
        SYNTHESIS_MODULE_VERSION: SynthesisModuleV1,
        SYNTHESIS_MODULE_V1ALPHA2_VERSION: SynthesisModuleV1Alpha2,
    }
    synthesis_modules = {
        item.module_id: synthesis_models[item.contract].model_validate_json(item.canonical_payload)
        for item in modules
        if item.contract in synthesis_models
    }
    persona_modules = {
        item.module_id: PersonasModuleV1.model_validate_json(item.canonical_payload)
        for item in modules
        if item.contract == PERSONAS_MODULE_VERSION
    }
    source_mapping_modules = {
        item.module_id: SourceMappingModuleV1.model_validate_json(item.canonical_payload)
        for item in modules
        if item.contract == SOURCE_MAPPING_MODULE_VERSION
    }
    entity_owner: dict[str, str] = {}
    relation_owner: dict[str, str] = {}
    for module_id, ontology in ontologies.items():
        for entity in ontology.entity_types:
            if entity.entity_type_id in entity_owner:
                raise ValueError(
                    f"entity type {entity.entity_type_id} is declared by multiple modules: "
                    f"{entity_owner[entity.entity_type_id]}, {module_id}"
                )
            entity_owner[entity.entity_type_id] = module_id
        for relation in ontology.relation_types:
            if relation.relation_type_id in relation_owner:
                raise ValueError(
                    f"relation type {relation.relation_type_id} is declared by multiple modules: "
                    f"{relation_owner[relation.relation_type_id]}, {module_id}"
                )
            relation_owner[relation.relation_type_id] = module_id

    mapping_owner: dict[str, str] = {}
    requirement_ids = {item.requirement_id for item in capability_requirements}
    authority_ids = {item.request_id for item in authority_requests}
    entity_by_id = {
        entity.entity_type_id: entity for ontology in ontologies.values() for entity in ontology.entity_types
    }
    for module_id, source_mapping in source_mapping_modules.items():
        direct_ontology_dependencies = set(module_by_id[module_id].depends_on) & set(ontologies)
        if not direct_ontology_dependencies:
            raise ValueError(f"source-mapping module {module_id} must directly depend on an ontology module")
        for mapping in source_mapping.mappings:
            owner = mapping_owner.get(mapping.mapping_id)
            if owner is not None:
                raise ValueError(
                    f"source mapping {mapping.mapping_id} is declared by multiple modules: {owner}, {module_id}"
                )
            mapping_owner[mapping.mapping_id] = module_id
            if mapping.capability_requirement_id not in requirement_ids:
                raise ValueError(f"source mapping {mapping.mapping_id} references an undeclared capability requirement")
            if mapping.authority_request_id not in authority_ids:
                raise ValueError(f"source mapping {mapping.mapping_id} references an undeclared authority request")
            ontology_owner = entity_owner.get(mapping.entity_type_id)
            if ontology_owner is None or ontology_owner not in direct_ontology_dependencies:
                raise ValueError(
                    f"source mapping {mapping.mapping_id} references entity type outside its direct "
                    f"ontology dependencies: {mapping.entity_type_id}"
                )
            entity = entity_by_id[mapping.entity_type_id]
            attributes = {item.attribute_id: item for item in entity.attributes}
            mapped_ids = {item.attribute_id for item in mapping.attribute_mappings}
            missing_required = sorted(
                item.attribute_id for item in entity.attributes if item.required and item.attribute_id not in mapped_ids
            )
            if missing_required:
                raise ValueError(f"source mapping {mapping.mapping_id} omits required attributes: {missing_required}")
            for attribute_mapping in mapping.attribute_mappings:
                target = attributes.get(attribute_mapping.attribute_id)
                if target is None:
                    raise ValueError(
                        f"source mapping {mapping.mapping_id} references unknown attribute "
                        f"{mapping.entity_type_id}.{attribute_mapping.attribute_id}"
                    )
                if attribute_mapping.transform is SourceMappingTransform.DECIMAL_TEXT_TO_NUMBER and (
                    target.value_type is not AttributeValueType.NUMBER or target.many
                ):
                    raise ValueError(
                        f"source mapping {mapping.mapping_id} uses decimal_text_to_number for an incompatible target"
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
                    raise ValueError(
                        f"source mapping {mapping.mapping_id} applies string constraints to an incompatible target"
                    )
                if attribute_mapping.character_set is not None and (
                    attribute_mapping.transform is not SourceMappingTransform.COPY
                    or target.value_type is not AttributeValueType.STRING
                ):
                    raise ValueError(
                        f"source mapping {mapping.mapping_id} applies character_set to an incompatible target"
                    )

    for module_id, ontology in ontologies.items():
        visible_modules = transitive_dependencies(module_id) | {module_id}
        visible_entities = {
            entity_id for entity_id, owner_module_id in entity_owner.items() if owner_module_id in visible_modules
        }
        for relation in ontology.relation_types:
            missing = (set(relation.source_entity_types) | set(relation.target_entity_types)) - visible_entities
            if missing:
                raise ValueError(
                    f"relation {relation.relation_type_id} references entity types outside its module dependencies: "
                    f"{sorted(missing)}"
                )

    detector_owner: dict[str, str] = {}
    for module_id, detection in detections.items():
        visible_modules = transitive_dependencies(module_id)
        visible_ontologies = [
            ontology for ontology_id, ontology in ontologies.items() if ontology_id in visible_modules
        ]
        visible_attributes = {
            entity.entity_type_id: {attribute.attribute_id: attribute for attribute in entity.attributes}
            for ontology in visible_ontologies
            for entity in ontology.entity_types
        }
        for rule in detection.numeric_delta_rules:
            owner = detector_owner.get(rule.detector_id)
            if owner is not None:
                raise ValueError(f"detector {rule.detector_id} is declared by multiple modules: {owner}, {module_id}")
            detector_owner[rule.detector_id] = module_id
            attributes = visible_attributes.get(rule.entity_type_id)
            if attributes is None:
                raise ValueError(
                    f"detector {rule.detector_id} references entity type outside its module dependencies: "
                    f"{rule.entity_type_id}"
                )
            attribute = attributes.get(rule.attribute_id)
            if attribute is None:
                raise ValueError(
                    f"detector {rule.detector_id} references unknown attribute "
                    f"{rule.entity_type_id}.{rule.attribute_id}"
                )
            if attribute.value_type not in {AttributeValueType.INTEGER, AttributeValueType.NUMBER}:
                raise ValueError(
                    f"numeric detector {rule.detector_id} requires an integer or number attribute, got "
                    f"{rule.entity_type_id}.{rule.attribute_id}:{attribute.value_type.value}"
                )
            missing_context = set(rule.context_attribute_ids) - set(attributes)
            if missing_context:
                raise ValueError(
                    f"numeric detector {rule.detector_id} references unknown comparison context "
                    f"attributes on {rule.entity_type_id}: {sorted(missing_context)}"
                )
        for rule in getattr(detection, "categorical_transition_rules", ()):
            owner = detector_owner.get(rule.detector_id)
            if owner is not None:
                raise ValueError(f"detector {rule.detector_id} is declared by multiple modules: {owner}, {module_id}")
            detector_owner[rule.detector_id] = module_id
            attributes = visible_attributes.get(rule.entity_type_id)
            if attributes is None:
                raise ValueError(
                    f"detector {rule.detector_id} references entity type outside its module dependencies: "
                    f"{rule.entity_type_id}"
                )
            attribute = attributes.get(rule.attribute_id)
            if attribute is None:
                raise ValueError(
                    f"detector {rule.detector_id} references unknown attribute "
                    f"{rule.entity_type_id}.{rule.attribute_id}"
                )
            if attribute.value_type is not AttributeValueType.STRING:
                raise ValueError(
                    f"categorical detector {rule.detector_id} requires a string attribute, got "
                    f"{rule.entity_type_id}.{rule.attribute_id}:{attribute.value_type.value}"
                )
            if attribute.many:
                raise ValueError(
                    f"categorical detector {rule.detector_id} requires a single-valued attribute, got "
                    f"{rule.entity_type_id}.{rule.attribute_id}"
                )
            missing_context = set(rule.context_attribute_ids) - set(attributes)
            if missing_context:
                raise ValueError(
                    f"categorical detector {rule.detector_id} references unknown comparison context "
                    f"attributes on {rule.entity_type_id}: {sorted(missing_context)}"
                )

    persona_owner: dict[str, str] = {}
    routing_owner: dict[str, str] = {}
    template_owner: dict[str, str] = {}
    for module_id, synthesis in synthesis_modules.items():
        for template in synthesis.brief_templates:
            owner = template_owner.get(template.template_id)
            if owner is not None:
                raise ValueError(
                    f"Brief template {template.template_id} is declared by multiple modules: {owner}, {module_id}"
                )
            template_owner[template.template_id] = module_id

    for module_id, personas in persona_modules.items():
        visible_modules = transitive_dependencies(module_id)
        visible_signal_types = {
            rule.signal_type
            for detection_id, detection in detections.items()
            if detection_id in visible_modules
            for rule in (
                tuple(detection.numeric_delta_rules) + tuple(getattr(detection, "categorical_transition_rules", ()))
            )
        }
        visible_template_ids = {
            template.template_id
            for synthesis_id, synthesis in synthesis_modules.items()
            if synthesis_id in visible_modules
            for template in synthesis.brief_templates
        }
        declared_personas = {persona.persona_id for persona in personas.personas}
        for persona in personas.personas:
            owner = persona_owner.get(persona.persona_id)
            if owner is not None:
                raise ValueError(f"persona {persona.persona_id} is declared by multiple modules: {owner}, {module_id}")
            persona_owner[persona.persona_id] = module_id
        for route in personas.signal_routing_rules:
            owner = routing_owner.get(route.routing_rule_id)
            if owner is not None:
                raise ValueError(
                    f"routing rule {route.routing_rule_id} is declared by multiple modules: {owner}, {module_id}"
                )
            routing_owner[route.routing_rule_id] = module_id
            if route.signal_type not in visible_signal_types:
                raise ValueError(
                    f"routing rule {route.routing_rule_id} references signal type outside its module "
                    f"dependencies: {route.signal_type}"
                )
            unknown_personas = set(route.persona_ids) - declared_personas
            if unknown_personas:
                raise ValueError(
                    f"routing rule {route.routing_rule_id} references unknown personas: {sorted(unknown_personas)}"
                )
            if route.brief_template_id is not None and route.brief_template_id not in visible_template_ids:
                raise ValueError(
                    f"routing rule {route.routing_rule_id} references Brief template outside its module "
                    f"dependencies: {route.brief_template_id}"
                )

    epistemic_models = {
        EPISTEMIC_STATUS_MODULE_VERSION: EpistemicStatusModuleV1,
        EPISTEMIC_STATUS_MODULE_V1ALPHA2_VERSION: EpistemicStatusModuleV1Alpha2,
    }
    epistemic_modules = {
        item.module_id: epistemic_models[item.contract].model_validate_json(item.canonical_payload)
        for item in modules
        if item.contract in epistemic_models
    }
    status_set_owner: dict[str, str] = {}
    status_template_owner: dict[str, str] = {}
    for module_id, epistemic in epistemic_modules.items():
        visible_modules = transitive_dependencies(module_id)
        visible_template_ids = {
            template.template_id
            for synthesis_id, synthesis in synthesis_modules.items()
            if synthesis_id in visible_modules
            for template in synthesis.brief_templates
        }
        if not visible_template_ids:
            raise ValueError(f"epistemic-status module {module_id} must depend on a Brief synthesis module")
        for status_set in epistemic.status_sets:
            owner = status_set_owner.get(status_set.status_set_id)
            if owner is not None:
                raise ValueError(
                    f"epistemic status set {status_set.status_set_id} is declared by multiple "
                    f"modules: {owner}, {module_id}"
                )
            status_set_owner[status_set.status_set_id] = module_id
            missing = set(status_set.brief_template_ids) - visible_template_ids
            if missing:
                raise ValueError(
                    f"epistemic status set {status_set.status_set_id} references Brief templates "
                    f"outside its module dependencies: {sorted(missing)}"
                )
            for template_id in status_set.brief_template_ids:
                template_owner_id = status_template_owner.get(template_id)
                if template_owner_id is not None:
                    raise ValueError(
                        f"Brief template {template_id} is governed by multiple epistemic status "
                        f"sets: {template_owner_id}, {status_set.status_set_id}"
                    )
                status_template_owner[template_id] = status_set.status_set_id

    feedback_policy_owner: dict[str, str] = {}
    for module_id, decision_outcomes in decision_outcome_modules.items():
        visible_modules = transitive_dependencies(module_id)
        visible_personas = {
            persona.persona_id
            for personas_id, personas in persona_modules.items()
            if personas_id in visible_modules
            for persona in personas.personas
        }
        visible_routes = {
            route.routing_rule_id: route
            for personas_id, personas in persona_modules.items()
            if personas_id in visible_modules
            for route in personas.signal_routing_rules
        }
        if not visible_routes:
            raise ValueError(f"decision-outcomes module {module_id} must depend on persona routing policy")
        for policy in decision_outcomes.feedback_policies:
            owner = feedback_policy_owner.get(policy.policy_id)
            if owner is not None:
                raise ValueError(
                    f"feedback policy {policy.policy_id} is declared by multiple modules: {owner}, {module_id}"
                )
            feedback_policy_owner[policy.policy_id] = module_id
            if policy.persona_id not in visible_personas:
                raise ValueError(
                    f"feedback policy {policy.policy_id} references persona outside its module "
                    f"dependencies: {policy.persona_id}"
                )
            route = visible_routes.get(policy.routing_rule_id)
            if route is None:
                raise ValueError(
                    f"feedback policy {policy.policy_id} references routing rule outside its module "
                    f"dependencies: {policy.routing_rule_id}"
                )
            if policy.persona_id not in route.persona_ids:
                raise ValueError(
                    f"feedback policy {policy.policy_id} persona is not eligible for routing rule "
                    f"{policy.routing_rule_id}"
                )


class CompiledDomainPackV1(FrozenContract):
    contract: Literal[
        "ace.intelligence.compiled-domain-pack/v1alpha1",
        "ace.intelligence.compiled-domain-pack/v1",
    ] = COMPILED_DOMAIN_PACK_VERSION
    compiler_contract: Literal[
        "ace.intelligence.pack-compiler/v1alpha1",
        "ace.intelligence.pack-compiler/v1",
    ] = PACK_COMPILER_VERSION
    intelligence_contract: Literal[
        "ace.intelligence.runtime/v1alpha1",
        "ace.intelligence.runtime/v1",
    ] = INTELLIGENCE_RUNTIME_VERSION
    manifest_contract: Literal[
        "ace.intelligence.domain-pack-manifest/v1alpha1",
        "ace.intelligence.domain-pack-manifest/v1",
    ] = DOMAIN_PACK_MANIFEST_VERSION
    declared_compatibility: PackCompatibilityRangeV1 | None = None
    metadata: PackMetadataV1
    modules: tuple[CompiledModuleV1, ...] = Field(min_length=1, max_length=MAX_DECLARATIONS)
    capability_requirements: tuple[CapabilityRequirementV1, ...] = Field(
        default_factory=tuple, max_length=MAX_DECLARATIONS
    )
    authority_requests: tuple[AuthorityRequestV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    overlay_slots: tuple[OverlaySlotDeclarationV1, ...] = Field(default_factory=tuple, max_length=MAX_DECLARATIONS)
    compiled_pack_id: str | None = None
    pack_digest: str | None = None

    @field_validator("modules")
    @classmethod
    def normalize_modules(cls, value: tuple[CompiledModuleV1, ...]) -> tuple[CompiledModuleV1, ...]:
        return sorted_unique(value, key=lambda item: item.module_id, label="compiled modules")

    @field_validator("capability_requirements")
    @classmethod
    def normalize_capabilities(cls, value: tuple[CapabilityRequirementV1, ...]) -> tuple[CapabilityRequirementV1, ...]:
        return sorted_unique(value, key=lambda item: item.requirement_id, label="capability requirements")

    @field_validator("authority_requests")
    @classmethod
    def normalize_authorities(cls, value: tuple[AuthorityRequestV1, ...]) -> tuple[AuthorityRequestV1, ...]:
        return sorted_unique(value, key=lambda item: item.request_id, label="authority requests")

    @field_validator("overlay_slots")
    @classmethod
    def normalize_overlay_slots(
        cls, value: tuple[OverlaySlotDeclarationV1, ...]
    ) -> tuple[OverlaySlotDeclarationV1, ...]:
        return sorted_unique(value, key=lambda item: item.slot_id, label="overlay slots")

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        if self.manifest_contract == DOMAIN_PACK_MANIFEST_VERSION and (
            self.contract != COMPILED_DOMAIN_PACK_VERSION
            or self.compiler_contract != PACK_COMPILER_VERSION
            or self.intelligence_contract != INTELLIGENCE_RUNTIME_VERSION
            or self.declared_compatibility is not None
        ):
            raise ValueError("v1alpha1 Pack IR requires the v1alpha1 compiler and runtime contracts")
        if self.manifest_contract == DOMAIN_PACK_MANIFEST_STABLE_VERSION and (
            self.contract != COMPILED_DOMAIN_PACK_STABLE_VERSION
            or self.compiler_contract != STABLE_PACK_COMPILER_VERSION
            or self.intelligence_contract != STABLE_INTELLIGENCE_RUNTIME_VERSION
            or self.declared_compatibility is None
        ):
            raise ValueError("stable Pack IR requires the stable compiler and runtime contracts")
        _validate_compiled_module_graph(
            self.modules,
            self.capability_requirements,
            self.authority_requests,
        )
        excluded = {"compiled_pack_id", "pack_digest"}
        if self.manifest_contract == DOMAIN_PACK_MANIFEST_VERSION:
            # Preserve every released v1alpha1 Pack IR identity byte-for-byte.  The
            # manifest contract was implicit in the historical material.
            excluded.add("manifest_contract")
            excluded.add("declared_compatibility")
        material = self.model_dump(mode="json", exclude=excluded)
        digest = canonical_hash(material)
        expected_digest = f"sha256:{digest}"
        expected_id = f"pack_ir:{digest[:32]}"
        if self.compiled_pack_id is not None and self.compiled_pack_id != expected_id:
            raise ValueError("compiled pack identity does not match exact material")
        if self.pack_digest is not None and self.pack_digest != expected_digest:
            raise ValueError("compiled pack digest does not match exact material")
        object.__setattr__(self, "compiled_pack_id", expected_id)
        object.__setattr__(self, "pack_digest", expected_digest)
        return self
