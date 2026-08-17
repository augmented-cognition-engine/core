"""Project one exact Intelligence build plan into the canonical product contract."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from pydantic import BaseModel

from ace.application.intelligence_build_planning import IntelligenceBuildPlanV1Alpha3
from ace.application.recorded_source_selection import RecordedSourceSelectionV1Alpha1
from ace.core.contracts import canonical_hash, canonical_json
from ace.intelligence.contracts.detection import (
    DETECTION_MODULE_V1ALPHA2_VERSION,
    DETECTION_MODULE_VERSION,
    DetectionModuleV1,
    DetectionModuleV1Alpha2,
)
from ace.intelligence.contracts.intelligence_builder_presentation import IntelligenceOnboardingProfileV1Alpha1
from ace.intelligence.contracts.pack import (
    ONTOLOGY_MODULE_VERSION,
    CompiledDomainPackV1,
    CompiledModuleV1,
    OntologyModuleV1,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourcePageV1Alpha1,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceRecordV1Alpha1,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    ObservationV1Alpha1,
    ShiftV1Alpha1,
    SignalV1Alpha1,
)
from ace.intelligence.contracts.synthesis import (
    SYNTHESIS_MODULE_V1ALPHA2_VERSION,
    SYNTHESIS_MODULE_VERSION,
    SynthesisModuleV1,
    SynthesisModuleV1Alpha2,
)
from ace.intelligence.contracts.system_projection import (
    DOMAIN_HEALTH_DIMENSION_ORDER,
    INITIALIZATION_STAGE_ORDER,
    BlueprintElementKind,
    BlueprintElementProjectionV1Alpha1,
    CoverageDimension,
    CoverageProjectionV1Alpha1,
    DerivationProjectionSetV1Alpha1,
    DomainHealthProjectionV1Alpha1,
    GeneratedBlueprintProjectionV1Alpha1,
    InitializationStageProjectionV1Alpha1,
    InitializationStageState,
    IntelligenceSystemProjectionV1Alpha1,
    PermissionReadinessState,
    ProjectionChangeOperation,
    ProjectionMaterialReferenceV1Alpha1,
    ProjectionMode,
    ProjectionSupport,
    ProjectionSupportStatementV1Alpha1,
    ProjectionValueV1Alpha1,
    ReviewableProjectionChangeV1Alpha1,
    SourceBindingProjectionV1Alpha1,
    SourceBindingState,
)


def _material_reference(
    *,
    material_contract: str,
    reference: str,
    digest: str,
) -> ProjectionMaterialReferenceV1Alpha1:
    return ProjectionMaterialReferenceV1Alpha1(
        material_contract=material_contract,
        reference=reference,
        digest=digest,
    )


def _module_reference(module: CompiledModuleV1) -> ProjectionMaterialReferenceV1Alpha1:
    return _material_reference(
        material_contract=module.contract,
        reference=f"pack_module:{module.module_id}",
        digest=module.module_digest,
    )


def _unsupported_value(
    reason: str,
    *,
    basis: Iterable[ProjectionMaterialReferenceV1Alpha1] = (),
) -> ProjectionValueV1Alpha1:
    return ProjectionValueV1Alpha1(
        support=ProjectionSupport.UNSUPPORTED,
        basis=tuple(basis),
        reason=reason,
    )


def _supported_value(
    *,
    support: ProjectionSupport,
    value: object,
    basis: Iterable[ProjectionMaterialReferenceV1Alpha1],
) -> ProjectionValueV1Alpha1:
    return ProjectionValueV1Alpha1(
        support=support,
        value=CanonicalJsonValueV1Alpha1(value_json=canonical_json(value)),
        basis=tuple(basis),
    )


def _title(identifier: str) -> str:
    return identifier.replace("_", " ").replace("-", " ").replace(".", " ").title()


def _element(
    *,
    kind: BlueprintElementKind,
    element_id: str,
    label: str,
    rationale: str,
    source_material: tuple[ProjectionMaterialReferenceV1Alpha1, ...],
) -> BlueprintElementProjectionV1Alpha1:
    return BlueprintElementProjectionV1Alpha1(
        kind=kind,
        element_id=element_id,
        label=label,
        rationale=rationale,
        source_material=source_material,
        confidence=_unsupported_value(
            "The current Pack and onboarding profile do not contract a blueprint-confidence score.",
            basis=source_material,
        ),
    )


def _blueprint_elements(
    *,
    plan: IntelligenceBuildPlanV1Alpha3,
    profile: IntelligenceOnboardingProfileV1Alpha1,
    pack: CompiledDomainPackV1,
) -> tuple[BlueprintElementProjectionV1Alpha1, ...]:
    outcome = next(item for item in profile.outcomes if item.outcome_id == plan.request.outcome_id)
    cadence = next(item for item in profile.cadences if item.cadence_id == plan.request.cadence_id)
    profile_ref = _material_reference(
        material_contract=profile.contract,
        reference=profile.profile_id,
        digest=str(profile.profile_digest),
    )
    elements: dict[tuple[BlueprintElementKind, str], BlueprintElementProjectionV1Alpha1] = {}

    def add(item: BlueprintElementProjectionV1Alpha1) -> None:
        key = (item.kind, item.element_id)
        prior = elements.get(key)
        if prior is None:
            elements[key] = item
            return
        if (prior.label, prior.rationale) != (item.label, item.rationale):
            raise ValueError(f"conflicting blueprint declarations for {item.kind.value}:{item.element_id}")
        elements[key] = _element(
            kind=item.kind,
            element_id=item.element_id,
            label=item.label,
            rationale=item.rationale,
            source_material=tuple({*prior.source_material, *item.source_material}),
        )

    for compiled in pack.modules:
        module_ref = _module_reference(compiled)
        if compiled.contract == ONTOLOGY_MODULE_VERSION:
            ontology = OntologyModuleV1.model_validate_json(compiled.canonical_payload)
            for entity in ontology.entity_types:
                add(
                    _element(
                        kind=BlueprintElementKind.ENTITY,
                        element_id=entity.entity_type_id,
                        label=entity.display_name or _title(entity.entity_type_id),
                        rationale="Declared by the exact installed Pack ontology.",
                        source_material=(module_ref,),
                    )
                )
            for relation in ontology.relation_types:
                add(
                    _element(
                        kind=BlueprintElementKind.RELATIONSHIP,
                        element_id=relation.relation_type_id,
                        label=_title(relation.relation_type_id),
                        rationale="Declared by the exact installed Pack ontology with bounded endpoint types.",
                        source_material=(module_ref,),
                    )
                )
        elif compiled.contract in {DETECTION_MODULE_VERSION, DETECTION_MODULE_V1ALPHA2_VERSION}:
            if compiled.contract == DETECTION_MODULE_VERSION:
                detection = DetectionModuleV1.model_validate_json(compiled.canonical_payload)
                rules = detection.numeric_delta_rules
            else:
                detection = DetectionModuleV1Alpha2.model_validate_json(compiled.canonical_payload)
                rules = (*detection.numeric_delta_rules, *detection.categorical_transition_rules)
            for rule in rules:
                add(
                    _element(
                        kind=BlueprintElementKind.EVENT,
                        element_id=rule.shift_type,
                        label=_title(rule.shift_type),
                        rationale="Projected from an exact Pack detector's material-event output.",
                        source_material=(module_ref,),
                    )
                )
                add(
                    _element(
                        kind=BlueprintElementKind.SIGNAL,
                        element_id=rule.signal_type,
                        label=_title(rule.signal_type),
                        rationale="Projected from an exact Pack detector's signal output.",
                        source_material=(module_ref,),
                    )
                )
        elif compiled.contract in {SYNTHESIS_MODULE_VERSION, SYNTHESIS_MODULE_V1ALPHA2_VERSION}:
            if compiled.contract == SYNTHESIS_MODULE_VERSION:
                synthesis = SynthesisModuleV1.model_validate_json(compiled.canonical_payload)
            else:
                synthesis = SynthesisModuleV1Alpha2.model_validate_json(compiled.canonical_payload)
            for template in synthesis.brief_templates:
                add(
                    _element(
                        kind=BlueprintElementKind.OUTPUT,
                        element_id=template.template_id,
                        label=template.display_name,
                        rationale="Declared by the exact installed Pack synthesis policy.",
                        source_material=(module_ref,),
                    )
                )

    add(
        _element(
            kind=BlueprintElementKind.QUESTION,
            element_id=f"question_{outcome.outcome_id}",
            label=outcome.label,
            rationale=outcome.description,
            source_material=(profile_ref,),
        )
    )
    add(
        _element(
            kind=BlueprintElementKind.UPDATE,
            element_id=f"cadence_{cadence.cadence_id}",
            label=cadence.label,
            rationale=cadence.description,
            source_material=(profile_ref,),
        )
    )
    declared_outputs = {item.element_id for item in elements.values() if item.kind is BlueprintElementKind.OUTPUT}
    labels_by_id = dict(zip(outcome.recommended_intelligence_ids, outcome.recommended_intelligence_labels))
    for intelligence_id in outcome.recommended_intelligence_ids:
        if intelligence_id not in declared_outputs:
            add(
                _element(
                    kind=BlueprintElementKind.OUTPUT,
                    element_id=intelligence_id,
                    label=labels_by_id.get(intelligence_id, _title(intelligence_id)),
                    rationale="Recommended by the exact selected onboarding outcome.",
                    source_material=(profile_ref,),
                )
            )
    return tuple(elements.values())


def _source_bindings(
    *,
    profile: IntelligenceOnboardingProfileV1Alpha1,
    pack: CompiledDomainPackV1,
    selections: tuple[RecordedSourceSelectionV1Alpha1, ...],
) -> tuple[SourceBindingProjectionV1Alpha1, ...]:
    groups = {item.source_group_id: item for item in profile.source_groups}
    pack_ref = _material_reference(
        material_contract=pack.contract,
        reference=str(pack.compiled_pack_id),
        digest=str(pack.pack_digest),
    )
    result = []
    for selection in selections:
        group = groups[selection.source_group_id]
        selection_ref = _material_reference(
            material_contract=selection.contract,
            reference=str(selection.selection_id),
            digest=str(selection.selection_digest),
        )
        result.append(
            SourceBindingProjectionV1Alpha1(
                binding_id=f"source_binding:{canonical_hash(selection_ref.model_dump(mode='json'))[:32]}",
                selection=selection_ref,
                source_group_id=selection.source_group_id,
                label=group.label,
                evidence_role=group.evidence_role,
                source_definition_ref=selection.source_definition_ref,
                source_type_ref=selection.source_type_ref,
                source_uri=selection.source_uri,
                mapping_id=selection.mapping_id,
                subject_binding_id=selection.subject_binding_id,
                entity_type_id=selection.entity_type_id,
                entity_ref=selection.entity_ref,
                access_requirement_label=group.access_label,
                binding_state=SourceBindingState.PROPOSED,
                permission_state=PermissionReadinessState.NOT_EVALUATED,
                readiness_state=PermissionReadinessState.NOT_EVALUATED,
                requirements=ProjectionSupportStatementV1Alpha1(
                    support=ProjectionSupport.UNSUPPORTED,
                    basis=(selection_ref, pack_ref),
                    reason=(
                        "The Pack declares capability and authority requirements globally but does not bind "
                        "them to this exact source selection."
                    ),
                ),
            )
        )
    return tuple(result)


def _coverage(
    *,
    elements: tuple[BlueprintElementProjectionV1Alpha1, ...],
    bindings: tuple[SourceBindingProjectionV1Alpha1, ...],
    pack: CompiledDomainPackV1,
) -> tuple[CoverageProjectionV1Alpha1, ...]:
    binding_ids_by_entity: dict[str, set[str]] = defaultdict(set)
    selection_refs_by_entity: dict[str, set[ProjectionMaterialReferenceV1Alpha1]] = defaultdict(set)
    for binding in bindings:
        binding_ids_by_entity[binding.entity_type_id].add(binding.binding_id)
        selection_refs_by_entity[binding.entity_type_id].add(binding.selection)

    detector_entities: dict[tuple[BlueprintElementKind, str], set[str]] = defaultdict(set)
    module_refs: dict[tuple[BlueprintElementKind, str], set[ProjectionMaterialReferenceV1Alpha1]] = defaultdict(set)
    for compiled in pack.modules:
        if compiled.contract not in {DETECTION_MODULE_VERSION, DETECTION_MODULE_V1ALPHA2_VERSION}:
            continue
        module_ref = _module_reference(compiled)
        if compiled.contract == DETECTION_MODULE_VERSION:
            detection = DetectionModuleV1.model_validate_json(compiled.canonical_payload)
            rules = detection.numeric_delta_rules
        else:
            detection = DetectionModuleV1Alpha2.model_validate_json(compiled.canonical_payload)
            rules = (*detection.numeric_delta_rules, *detection.categorical_transition_rules)
        for rule in rules:
            for key in (
                (BlueprintElementKind.EVENT, rule.shift_type),
                (BlueprintElementKind.SIGNAL, rule.signal_type),
            ):
                detector_entities[key].add(rule.entity_type_id)
                module_refs[key].add(module_ref)

    dimension_by_kind = {
        BlueprintElementKind.ENTITY: CoverageDimension.ENTITY,
        BlueprintElementKind.EVENT: CoverageDimension.EVENT,
        BlueprintElementKind.SIGNAL: CoverageDimension.SIGNAL,
    }
    rows = []
    for element in elements:
        dimension = dimension_by_kind.get(element.kind)
        if dimension is None:
            continue
        entity_types = (
            {element.element_id}
            if element.kind is BlueprintElementKind.ENTITY
            else detector_entities[(element.kind, element.element_id)]
        )
        binding_ids = sorted(
            {binding_id for entity_type_id in entity_types for binding_id in binding_ids_by_entity[entity_type_id]}
        )
        basis = set(element.source_material)
        for entity_type_id in entity_types:
            basis.update(selection_refs_by_entity[entity_type_id])
        basis.update(module_refs[(element.kind, element.element_id)])
        rows.append(
            CoverageProjectionV1Alpha1(
                dimension=dimension,
                target_ref=str(element.element_ref),
                target_label=element.label,
                source_binding_ids=tuple(binding_ids),
                predicted=_unsupported_value(
                    "No installed predicted-coverage estimator contract is bound to this plan.",
                    basis=basis,
                ),
                observed=_unsupported_value(
                    "Observed coverage is unavailable until governed evidence is admitted and evaluated.",
                    basis=basis,
                ),
            )
        )
    return tuple(rows)


def _review_changes(
    elements: tuple[BlueprintElementProjectionV1Alpha1, ...],
) -> tuple[ReviewableProjectionChangeV1Alpha1, ...]:
    return tuple(
        ReviewableProjectionChangeV1Alpha1(
            operation=ProjectionChangeOperation.ADD,
            target_ref=str(element.element_ref),
            after=CanonicalJsonValueV1Alpha1(value_json=canonical_json(element.model_dump(mode="json"))),
            rationale=(
                "The exact plan contains no prior accepted blueprint; this generated element is a proposed "
                "addition and requires explicit review."
            ),
            expected_effect=_unsupported_value(
                "The current contracts do not project a quantified effect for this blueprint change.",
                basis=element.source_material,
            ),
        )
        for element in elements
    )


_COVERAGE_RESOURCE_KINDS = frozenset(
    {
        IntelligenceResourceKind.OBSERVATION,
        IntelligenceResourceKind.ENTITY,
        IntelligenceResourceKind.SHIFT,
        IntelligenceResourceKind.SIGNAL,
    }
)
DOMAIN_HEALTH_RESOURCE_KINDS: tuple[IntelligenceResourceKind, ...] = tuple(
    sorted((*_COVERAGE_RESOURCE_KINDS, IntelligenceResourceKind.SOURCE_HEALTH), key=lambda item: item.value)
)


def _unique_basis(
    values: Iterable[ProjectionMaterialReferenceV1Alpha1],
) -> tuple[ProjectionMaterialReferenceV1Alpha1, ...]:
    exact = {(item.material_contract, item.reference, item.digest): item for item in values}
    return tuple(exact[key] for key in sorted(exact))


def _resource_reference(record: IntelligenceResourceRecordV1Alpha1) -> ProjectionMaterialReferenceV1Alpha1:
    reference = record.reference
    return _material_reference(
        material_contract=reference.resource_contract,
        reference=reference.resource_id,
        digest=reference.resource_digest,
    )


def _page_reference(page: IntelligenceResourcePageV1Alpha1) -> ProjectionMaterialReferenceV1Alpha1:
    return _material_reference(
        material_contract=page.contract,
        reference=str(page.page_id),
        digest=str(page.page_digest),
    )


def _decode_runtime_resource(record: IntelligenceResourceRecordV1Alpha1) -> BaseModel | None:
    models: dict[IntelligenceResourceKind, type[BaseModel]] = {
        IntelligenceResourceKind.OBSERVATION: ObservationV1Alpha1,
        IntelligenceResourceKind.ENTITY: EntitySnapshotV1Alpha1,
        IntelligenceResourceKind.SHIFT: ShiftV1Alpha1,
        IntelligenceResourceKind.SIGNAL: SignalV1Alpha1,
    }
    model = models.get(record.reference.resource_kind)
    if model is None:
        return None
    if record.payload is None:
        raise ValueError("runtime Intelligence resource omitted its exact payload")
    value = model.model_validate_json(record.payload.value_json)
    if (
        value.product_id != record.reference.product_id
        or value.resource_id != record.reference.resource_id
        or value.resource_digest != record.reference.resource_digest
        or value.contract != record.reference.resource_contract
        or value.as_of != record.reference.as_of
    ):
        raise ValueError("runtime Intelligence resource crossed its exact public reference")
    return value


def _runtime_projection_gap(
    *,
    query: IntelligenceResourceQueryV1Alpha1,
    page: IntelligenceResourcePageV1Alpha1,
    required_kinds: frozenset[IntelligenceResourceKind],
) -> str | None:
    if query.cursor is not None:
        return "Domain Health requires the first complete resource page, not a continuation page."
    if query.subject_refs:
        return "A subject-filtered resource query cannot support a domain-wide health projection."
    if page.next_cursor is not None:
        return "The resource query has more pages; domain-wide health remains unsupported until closure is complete."
    if page.state is IntelligenceResourcePageState.DEGRADED:
        return (
            "The authoritative resource read is degraded; Domain Health fails closed instead of scoring partial state."
        )
    missing = required_kinds - set(query.resource_kinds)
    if missing:
        labels = ", ".join(sorted(item.value for item in missing))
        return f"The exact resource query omitted required kinds: {labels}."
    return None


def _live_observation_bindings(
    *,
    record: IntelligenceResourceRecordV1Alpha1,
    records: dict[tuple[IntelligenceResourceKind, str, str], IntelligenceResourceRecordV1Alpha1],
    projection: IntelligenceSystemProjectionV1Alpha1,
    activation_revision: ActivationRevisionReferenceV1Alpha1 | None,
) -> tuple[set[str], set[ProjectionMaterialReferenceV1Alpha1]]:
    bindings = {(item.source_definition_ref, item.mapping_id): item.binding_id for item in projection.source_bindings}
    found: set[str] = set()
    basis: set[ProjectionMaterialReferenceV1Alpha1] = set()
    pending = [record]
    seen: set[tuple[IntelligenceResourceKind, str, str]] = set()
    while pending:
        current = pending.pop()
        key = (
            current.reference.resource_kind,
            current.reference.resource_id,
            current.reference.resource_digest,
        )
        if key in seen:
            continue
        seen.add(key)
        decoded = _decode_runtime_resource(current)
        if (
            activation_revision is not None
            and decoded is not None
            and decoded.activation_revision != activation_revision
        ):
            # Pack/mapping lineage alone cannot prove this resource belongs to the
            # accepted session's active activation; a mismatched resource (and its
            # upstream lineage) is excluded rather than counted as live evidence.
            continue
        basis.add(_resource_reference(current))
        if isinstance(decoded, ObservationV1Alpha1):
            mapping = decoded.source_mapping
            if (
                decoded.mode is IntelligenceResourceMode.LIVE
                and mapping is not None
                and mapping.compiled_pack_id == projection.pack.compiled_pack_id
                and mapping.pack_digest == projection.pack.pack_digest
            ):
                binding_id = bindings.get((decoded.source_ref, mapping.mapping_id))
                if binding_id is not None:
                    found.add(binding_id)
            continue
        for upstream in current.provenance:
            if upstream.resource_kind not in _COVERAGE_RESOURCE_KINDS:
                continue
            exact = records.get((upstream.resource_kind, upstream.resource_id, upstream.resource_digest))
            if exact is not None:
                pending.append(exact)
    return found, basis


def _observed_coverage(
    *,
    projection: IntelligenceSystemProjectionV1Alpha1,
    query: IntelligenceResourceQueryV1Alpha1,
    page: IntelligenceResourcePageV1Alpha1,
    activation_revision: ActivationRevisionReferenceV1Alpha1 | None,
) -> tuple[tuple[CoverageProjectionV1Alpha1, ...], ProjectionValueV1Alpha1]:
    page_ref = _page_reference(page)
    gap = _runtime_projection_gap(query=query, page=page, required_kinds=_COVERAGE_RESOURCE_KINDS)
    if gap is not None:
        rows = tuple(
            item.model_copy(
                update={
                    "observed": _unsupported_value(gap, basis=(page_ref, projection.plan)),
                }
            )
            for item in projection.coverage
        )
        return rows, _unsupported_value(gap, basis=(page_ref, projection.plan))

    exact_records = {
        (item.reference.resource_kind, item.reference.resource_id, item.reference.resource_digest): item
        for item in page.items
        if item.reference.resource_kind in _COVERAGE_RESOURCE_KINDS
    }
    decoded: dict[tuple[IntelligenceResourceKind, str, str], BaseModel] = {}
    try:
        for key, record in exact_records.items():
            value = _decode_runtime_resource(record)
            if value is not None:
                decoded[key] = value
    except ValueError:
        reason = "At least one coverage resource failed exact contract replay; observed coverage fails closed."
        rows = tuple(
            item.model_copy(
                update={
                    "observed": _unsupported_value(reason, basis=(page_ref, projection.plan)),
                }
            )
            for item in projection.coverage
        )
        return rows, _unsupported_value(reason, basis=(page_ref, projection.plan))

    elements = {str(item.element_ref): item for item in projection.blueprint.elements}
    candidates: dict[tuple[CoverageDimension, str], list[IntelligenceResourceRecordV1Alpha1]] = defaultdict(list)
    for key, value in decoded.items():
        if getattr(value, "mode", None) is not IntelligenceResourceMode.LIVE:
            continue
        if isinstance(value, EntitySnapshotV1Alpha1):
            candidate_key = (CoverageDimension.ENTITY, value.entity_type_ref)
        elif isinstance(value, ShiftV1Alpha1):
            candidate_key = (CoverageDimension.EVENT, value.shift_type_ref)
        elif isinstance(value, SignalV1Alpha1):
            candidate_key = (CoverageDimension.SIGNAL, value.signal_type_ref)
        else:
            continue
        candidates[candidate_key].append(exact_records[key])

    rows: list[CoverageProjectionV1Alpha1] = []
    target_states: list[dict[str, object]] = []
    domain_basis: set[ProjectionMaterialReferenceV1Alpha1] = {page_ref, projection.plan}
    for row in projection.coverage:
        element = elements[row.target_ref]
        matched_records: list[IntelligenceResourceRecordV1Alpha1] = []
        matched_bindings: set[str] = set()
        matched_basis: set[ProjectionMaterialReferenceV1Alpha1] = {page_ref, projection.plan}
        for candidate in candidates[(row.dimension, element.element_id)]:
            binding_ids, candidate_basis = _live_observation_bindings(
                record=candidate,
                records=exact_records,
                projection=projection,
                activation_revision=activation_revision,
            )
            exact_bindings = binding_ids & set(row.source_binding_ids)
            if not exact_bindings:
                continue
            matched_records.append(candidate)
            matched_bindings.update(exact_bindings)
            matched_basis.update(candidate_basis)
        state = "observed" if matched_records else "not_observed"
        revisions = [
            {
                "resource_kind": item.reference.resource_kind.value,
                "resource_id": item.reference.resource_id,
                "resource_digest": item.reference.resource_digest,
                "as_of": item.reference.as_of.isoformat(),
            }
            for item in sorted(
                matched_records,
                key=lambda item: (
                    item.reference.resource_kind.value,
                    item.reference.resource_id,
                    item.reference.resource_digest,
                ),
            )
        ]
        observed = _supported_value(
            support=ProjectionSupport.OBSERVED,
            value={
                "state": state,
                "resource_revisions": revisions,
                "source_binding_ids": sorted(matched_bindings),
                "as_of": query.as_of.isoformat(),
                "interpretation": (
                    "Literal exact Pack-bound, activation-revision-bound resource observation state; not a "
                    "completeness, confidence, or quality score."
                    if activation_revision is not None
                    else (
                        "Literal exact Pack-bound resource observation state; not a completeness, confidence, or "
                        "quality score. No accepted-session activation-revision association was supplied, so this "
                        "state is not yet bound to one exact live activation."
                    )
                ),
            },
            basis=_unique_basis(matched_basis),
        )
        rows.append(row.model_copy(update={"observed": observed}))
        domain_basis.update(observed.basis)
        target_states.append(
            {
                "dimension": row.dimension.value,
                "target_ref": row.target_ref,
                "state": state,
                "source_binding_ids": sorted(matched_bindings),
                "resource_refs": [item["resource_id"] for item in revisions],
            }
        )
    coverage_health = _supported_value(
        support=ProjectionSupport.DERIVED,
        value={
            "state": "observed_target_state",
            "as_of": query.as_of.isoformat(),
            "targets": target_states,
            "interpretation": (
                "Each target is matched through exact live resource lineage to the reviewed Pack and source binding. "
                "No percentage or quality score is inferred from presence."
            ),
        },
        basis=_unique_basis(domain_basis),
    )
    return tuple(rows), coverage_health


def _source_health(
    *,
    projection: IntelligenceSystemProjectionV1Alpha1,
    query: IntelligenceResourceQueryV1Alpha1,
    page: IntelligenceResourcePageV1Alpha1,
) -> ProjectionValueV1Alpha1:
    page_ref = _page_reference(page)
    gap = _runtime_projection_gap(
        query=query,
        page=page,
        required_kinds=frozenset({IntelligenceResourceKind.SOURCE_HEALTH}),
    )
    if gap is not None:
        return _unsupported_value(gap, basis=(page_ref, projection.plan))
    records = [item for item in page.items if item.reference.resource_kind is IntelligenceResourceKind.SOURCE_HEALTH]
    states: list[dict[str, object]] = []
    basis: set[ProjectionMaterialReferenceV1Alpha1] = {page_ref, projection.plan}
    for binding in projection.source_bindings:
        matches: list[tuple[IntelligenceResourceRecordV1Alpha1, dict[str, object]]] = []
        for record in records:
            if record.payload is None:
                continue
            payload = record.payload.parsed_value()
            if not isinstance(payload, dict):
                continue
            if (
                payload.get("reviewed_selection_id") == binding.selection.reference
                and payload.get("reviewed_selection_digest") == binding.selection.digest
            ):
                matches.append((record, payload))
        if not matches:
            states.append(
                {
                    "binding_id": binding.binding_id,
                    "state": "not_observed",
                    "interpretation": "No exact source-health revision names this reviewed source selection.",
                }
            )
            continue
        record, payload = max(
            matches,
            key=lambda item: (item[0].reference.available_at, item[0].reference.revision),
        )
        basis.add(_resource_reference(record))
        states.append(
            {
                "binding_id": binding.binding_id,
                "state": "observed",
                "resource_id": record.reference.resource_id,
                "resource_digest": record.reference.resource_digest,
                "availability": record.availability.value,
                "health_basis": payload.get("health_basis"),
                "readiness_state": payload.get("readiness_state"),
                "credential_state": payload.get("credential_state"),
                "permission_state": payload.get("permission_state"),
                "activation_state": payload.get("activation_state"),
                "admission_state": payload.get("admission_state"),
                "retry_state": payload.get("retry_state"),
                "last_success_at": payload.get("last_success_at"),
                "last_error": payload.get("last_error"),
                "freshness": payload.get("freshness"),
                "freshness_verified": payload.get("freshness_verified"),
            }
        )
    return _supported_value(
        support=ProjectionSupport.OBSERVED,
        value={
            "state": "observed_binding_state",
            "as_of": query.as_of.isoformat(),
            "bindings": states,
            "interpretation": (
                "Literal readiness, admission, retry, and freshness-verification state per reviewed binding; "
                "resource presence is not treated as healthy."
            ),
        },
        basis=_unique_basis(basis),
    )


def project_intelligence_system_resource_state(
    *,
    projection: IntelligenceSystemProjectionV1Alpha1,
    query: IntelligenceResourceQueryV1Alpha1,
    page: IntelligenceResourcePageV1Alpha1,
    activation_revision: ActivationRevisionReferenceV1Alpha1 | None = None,
) -> IntelligenceSystemProjectionV1Alpha1:
    """Enrich the canonical system projection from one authorized, closed resource read.

    The function preserves predicted coverage. It only observes exact runtime
    material; activation authority remains outside this read model.

    ``activation_revision`` is the exact accepted-session activation-revision
    association resolved by
    :func:`ace.application.domain_activation_plan.resolve_live_activation_revision_for_session`
    (or an equivalent exact reload). When omitted, behavior is unchanged from
    the proposal-only aggregator: the input projection mode is preserved and
    observed coverage is Pack/mapping-bound only. When supplied, every
    observed resource must also carry this exact ``activation_revision``
    (point-of-use revalidated per resource; a stale, cross-product, or
    altered resource is silently excluded, never counted as live evidence).
    The projection is only promoted to ``ProjectionMode.LIVE`` once this
    association is present *and* the resource read fully closes (first page,
    unfiltered, undegraded, every required kind present) — closing the first
    of the two remaining runtime dependencies named in
    ``docs/design/atrium-live-domain-health-projection-v1.md``. Multi-page
    domain closure beyond 200 records remains the other, explicit, unclosed
    dependency; this function continues to fail closed for a continuation
    page.
    """

    exact_projection = IntelligenceSystemProjectionV1Alpha1.model_validate(projection.model_dump(mode="python"))
    exact_query = IntelligenceResourceQueryV1Alpha1.model_validate(query.model_dump(mode="python"))
    exact_page = IntelligenceResourcePageV1Alpha1.model_validate(page.model_dump(mode="python"))
    if (
        exact_projection.product_id != exact_query.product_id
        or exact_projection.product_id != exact_page.product_id
        or exact_page.query_id != exact_query.query_id
        or exact_page.query_digest != exact_query.query_digest
        or exact_page.as_of != exact_query.as_of
        or exact_page.available_at != exact_query.available_at
    ):
        raise ValueError("runtime Domain Health crossed the exact system or resource query")

    exact_activation_revision: ActivationRevisionReferenceV1Alpha1 | None = None
    if activation_revision is not None:
        exact_activation_revision = ActivationRevisionReferenceV1Alpha1.model_validate(
            activation_revision.model_dump(mode="python")
        )
        if exact_activation_revision.product_id != exact_projection.product_id:
            raise ValueError("runtime Domain Health activation revision crossed the exact system product")

    coverage, coverage_health = _observed_coverage(
        projection=exact_projection,
        query=exact_query,
        page=exact_page,
        activation_revision=exact_activation_revision,
    )
    source_health = _source_health(projection=exact_projection, query=exact_query, page=exact_page)
    page_ref = _page_reference(exact_page)
    reasons = {
        "freshness": (
            "Exact observations expose timestamps and recorded admissions expose freshness verification, but "
            "the selected cadence has no contracted machine evaluation window."
        ),
        "confidence": (
            "Exact resources carry per-resource confidence, but no contracted domain aggregation policy exists."
        ),
        "conflicts": "The current resource plane has no authoritative typed Conflict projection contributor.",
        "resolution": "No exact entity, relationship, and event resolution-quality projection is available.",
        "maintenance_health": (
            "Activation and monitor lifecycle state do not measure missed cycles, failures, or maintenance quality."
        ),
        "historical_depth": (
            "Immutable revisions expose history, but no contract defines which revisions are comparable domain history."
        ),
    }
    values = {
        "coverage": coverage_health,
        "source_health": source_health,
        **{
            name: _unsupported_value(reason, basis=(page_ref, exact_projection.plan))
            for name, reason in reasons.items()
        },
    }
    domain_health = tuple(
        DomainHealthProjectionV1Alpha1(dimension=dimension, value=values[dimension.value])
        for dimension in DOMAIN_HEALTH_DIMENSION_ORDER
    )
    stale_gaps = {
        "Predicted and observed coverage remain distinct and unsupported by this plan projection.",
        "All eight Domain Health dimensions require authoritative runtime projections before scoring.",
    }
    gaps = [item for item in exact_projection.gaps if item not in stale_gaps]
    gaps.extend(
        (
            "Predicted coverage remains unsupported; observed coverage reports exact target state without a score.",
            "Freshness, confidence, conflicts, resolution, maintenance health, and historical depth remain explicit architecture dependencies.",
        )
    )

    closure_gap = _runtime_projection_gap(
        query=exact_query,
        page=exact_page,
        required_kinds=frozenset(DOMAIN_HEALTH_RESOURCE_KINDS),
    )
    live = exact_activation_revision is not None and closure_gap is None
    resolved_mode = ProjectionMode.LIVE if live else exact_projection.mode
    if exact_activation_revision is None:
        gaps.append(
            "No accepted-session activation-revision association was supplied; mode remains "
            f"{exact_projection.mode.value} until an exact live activation revision is resolved and bound."
        )
    elif closure_gap is not None:
        gaps.append(
            "An exact live activation revision is bound to this accepted session, but the resource read did not "
            f"fully close ({closure_gap}); mode remains {exact_projection.mode.value} until multi-page domain "
            "closure is contracted."
        )

    material = exact_projection.model_dump(
        mode="python",
        exclude={
            "projection_id",
            "projection_digest",
            "coverage",
            "domain_health",
            "generated_at",
            "gaps",
            "mode",
            "activation_revision",
        },
    )
    return IntelligenceSystemProjectionV1Alpha1(
        **material,
        mode=resolved_mode,
        coverage=coverage,
        domain_health=domain_health,
        activation_revision=exact_activation_revision if live else None,
        generated_at=exact_page.evaluated_at,
        gaps=tuple(gaps),
    )


def project_intelligence_system_plan(
    *,
    plan: IntelligenceBuildPlanV1Alpha3,
    profile: IntelligenceOnboardingProfileV1Alpha1,
    pack: CompiledDomainPackV1,
) -> IntelligenceSystemProjectionV1Alpha1:
    """Build a truthful proposal projection from exact installed material only."""

    if plan.request.profile_id != profile.profile_id or plan.request.profile_digest != profile.profile_digest:
        raise ValueError("system projection crossed the exact onboarding profile")
    if (
        plan.pack_reference.compiled_pack_id != pack.compiled_pack_id
        or plan.pack_reference.pack_digest != pack.pack_digest
    ):
        raise ValueError("system projection crossed the exact compiled Pack")
    outcome_ids = {item.outcome_id for item in profile.outcomes}
    cadence_ids = {item.cadence_id for item in profile.cadences}
    if plan.request.outcome_id not in outcome_ids or plan.request.cadence_id not in cadence_ids:
        raise ValueError("system projection crossed installed onboarding selections")

    request_ref = _material_reference(
        material_contract=plan.request.contract,
        reference=str(plan.request.request_id),
        digest=str(plan.request.request_digest),
    )
    plan_ref = _material_reference(
        material_contract=plan.contract,
        reference=str(plan.plan_id),
        digest=str(plan.plan_digest),
    )
    pack_ref = _material_reference(
        material_contract=pack.contract,
        reference=str(pack.compiled_pack_id),
        digest=str(pack.pack_digest),
    )
    elements = _blueprint_elements(plan=plan, profile=profile, pack=pack)
    blueprint_gaps = (
        "Blueprint confidence is not scored by the current Pack or onboarding profile contracts.",
        "Downstream consumer bindings are not declared by the current build-plan contract.",
    )
    blueprint = GeneratedBlueprintProjectionV1Alpha1(
        plan=plan_ref,
        request=request_ref,
        pack=plan.pack_reference,
        subject=plan.request.subject,
        elements=elements,
        gaps=blueprint_gaps,
    )
    bindings = _source_bindings(
        profile=profile,
        pack=pack,
        selections=plan.recorded_source_selections,
    )
    coverage = _coverage(elements=elements, bindings=bindings, pack=pack)
    initialization = tuple(
        InitializationStageProjectionV1Alpha1(
            sequence=index,
            stage=stage,
            state=(
                InitializationStageState.COMPLETE
                if index == 1
                else InitializationStageState.IN_PROGRESS
                if index == 2
                else InitializationStageState.PENDING
            ),
            detail=(
                "Generated from the exact installed Pack and onboarding profile."
                if index == 1
                else "Awaiting explicit review; this projection grants no activation authority."
                if index == 2
                else "Not started; completion requires a durable governed runtime artifact."
            ),
            basis=(plan_ref, pack_ref) if index <= 2 else (),
        )
        for index, stage in enumerate(INITIALIZATION_STAGE_ORDER, start=1)
    )
    health_reason = {
        "coverage": "No predicted or observed domain-coverage measurement contract is bound.",
        "freshness": "No domain-level cadence-relative freshness aggregation is bound.",
        "confidence": "No domain-level confidence aggregation is bound.",
        "conflicts": "No typed domain conflict projection is bound.",
        "resolution": "No entity, relationship, and event resolution-quality projection is bound.",
        "source_health": "Source selections are proposal material; live source health is not evaluated.",
        "maintenance_health": "Maintenance has not been activated and no maintenance-health projection is bound.",
        "historical_depth": "No comparable-history depth projection is bound.",
    }
    domain_health = tuple(
        DomainHealthProjectionV1Alpha1(
            dimension=dimension,
            value=_unsupported_value(health_reason[dimension.value], basis=(plan_ref, pack_ref)),
        )
        for dimension in DOMAIN_HEALTH_DIMENSION_ORDER
    )
    gaps = [
        "Per-binding capability and authority requirements are not declared by the Pack contract.",
        "Predicted and observed coverage remain distinct and unsupported by this plan projection.",
        "Evidence-to-conclusion derivation becomes available only from exact runtime resource lineage.",
        "All eight Domain Health dimensions require authoritative runtime projections before scoring.",
    ]
    if pack.capability_requirements:
        gaps.append("Pack capability requirements remain unassigned to exact source bindings.")
    if pack.authority_requests:
        gaps.append("Pack authority requests remain unassigned to exact source bindings.")
    return IntelligenceSystemProjectionV1Alpha1(
        product_id=plan.request.product_id,
        mode=ProjectionMode.PROPOSED,
        plan=plan_ref,
        request=request_ref,
        pack=plan.pack_reference,
        blueprint=blueprint,
        changes=_review_changes(elements),
        source_bindings=bindings,
        unassigned_capability_requirement_ids=tuple(item.requirement_id for item in pack.capability_requirements),
        unassigned_authority_request_ids=tuple(item.request_id for item in pack.authority_requests),
        coverage=coverage,
        initialization=initialization,
        derivations=DerivationProjectionSetV1Alpha1(
            availability=ProjectionSupportStatementV1Alpha1(
                support=ProjectionSupport.UNSUPPORTED,
                basis=(plan_ref,),
                reason=(
                    "A proposal has no intelligence conclusion. Derivation requires exact admitted runtime "
                    "resources and lineage."
                ),
            ),
        ),
        domain_health=domain_health,
        generated_at=plan.request.requested_at,
        gaps=tuple(gaps),
    )


__all__ = [
    "DOMAIN_HEALTH_RESOURCE_KINDS",
    "project_intelligence_system_plan",
    "project_intelligence_system_resource_state",
]
