from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ace.application.intelligence_build_planning import IntelligenceBuildPlanV1Alpha3
from ace.application.intelligence_system_projection import (
    DOMAIN_HEALTH_RESOURCE_KINDS,
    project_intelligence_system_plan,
    project_intelligence_system_resource_state,
)
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourcePageState,
    IntelligenceResourcePageV1Alpha1,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    EntitySnapshotV1Alpha1,
    EvidenceAcquisitionMode,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageResourceKind,
    ObservationV1Alpha1,
    SourceMappingReferenceV1Alpha1,
)
from ace.intelligence.contracts.system_projection import (
    CoverageDimension,
    DomainHealthDimension,
    ProjectionMode,
    ProjectionSupport,
)
from tests.test_api_intelligence_build_plan import PACK, PROFILE, _Planner, _request

pytestmark = pytest.mark.unit


def _activation(product_id: str, *, digest_char: str = "a") -> ActivationRevisionReferenceV1Alpha1:
    digest = "sha256:" + digest_char * 64
    activation_key = "personal_intelligence"
    return ActivationRevisionReferenceV1Alpha1(
        product_id=product_id,
        activation_key=activation_key,
        activation_id=f"domain_activation:{canonical_hash([product_id, activation_key])[:32]}",
        revision=1,
        revision_id="activation_revision:" + digest_char * 32,
        revision_digest=digest,
    )


def _reference(resource, kind: IntelligenceResourceKind) -> IntelligenceResourceReferenceV1Alpha1:
    available_at = resource.ingested_at if isinstance(resource, ObservationV1Alpha1) else resource.projected_at
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=resource.product_id,
        resource_kind=kind,
        resource_id=str(resource.resource_id),
        resource_digest=str(resource.resource_digest),
        resource_contract=resource.contract,
        revision=1,
        as_of=resource.as_of,
        available_at=available_at,
    )


def _record(resource, kind: IntelligenceResourceKind) -> IntelligenceResourceRecordV1Alpha1:
    reference = _reference(resource, kind)
    provenance = tuple(
        IntelligenceResourceReferenceV1Alpha1(
            product_id=resource.product_id,
            resource_kind={
                LineageResourceKind.OBSERVATION: IntelligenceResourceKind.OBSERVATION,
                LineageResourceKind.ENTITY_SNAPSHOT: IntelligenceResourceKind.ENTITY,
            }[item.resource_kind],
            resource_id=item.resource_id,
            resource_digest=item.resource_digest,
            resource_contract={
                LineageResourceKind.OBSERVATION: "ace.intelligence.observation/v1alpha1",
                LineageResourceKind.ENTITY_SNAPSHOT: "ace.intelligence.entity-snapshot/v1alpha1",
            }[item.resource_kind],
            revision=1,
            as_of=item.resource_as_of,
            available_at=item.resource_available_at,
        )
        for item in resource.lineage
    )
    return IntelligenceResourceRecordV1Alpha1(
        reference=reference,
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=reference.resource_id,
        subject_refs=getattr(resource, "subject_refs", (getattr(resource, "entity_ref", "entity:unknown"),)),
        provenance=provenance,
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(resource.model_dump(mode="json"))),
    )


def _source_health_record(*, projection, at: datetime) -> IntelligenceResourceRecordV1Alpha1:
    binding = projection.source_bindings[0]
    payload = {
        "health_basis": "recorded_admission",
        "readiness_state": "ready",
        "credential_state": "not_applicable",
        "permission_state": "approved",
        "activation_state": "active",
        "admission_state": "admitted",
        "retry_state": "not_retrying",
        "last_success_at": at.isoformat(),
        "last_error": None,
        "freshness": "unverified",
        "freshness_verified": False,
        "reviewed_selection_id": binding.selection.reference,
        "reviewed_selection_digest": binding.selection.digest,
    }
    return IntelligenceResourceRecordV1Alpha1(
        reference=IntelligenceResourceReferenceV1Alpha1(
            product_id=projection.product_id,
            resource_kind=IntelligenceResourceKind.SOURCE_HEALTH,
            resource_id="source_health:reviewed-selection",
            resource_digest="sha256:" + "f" * 64,
            resource_contract="ace.intelligence.recorded-source-acquisition-receipt/v1alpha2",
            revision=1,
            as_of=at,
            available_at=at,
        ),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title="Recorded source ready",
        subject_refs=(binding.selection.reference,),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(payload)),
    )


def _query_and_page(*, projection, records, now: datetime, degraded: bool = False, filtered: bool = False):
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=projection.product_id,
        actor_ref="principal:personal-analyst",
        authentication_receipt_ref="authentication_receipt:domain-health",
        authentication_receipt_digest="sha256:" + "b" * 64,
        authenticated_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(minutes=30),
    )
    query = IntelligenceResourceQueryV1Alpha1(
        authenticated_context=context,
        product_id=projection.product_id,
        authority_grant_ref="authority_grant:resource-read",
        resource_kinds=DOMAIN_HEALTH_RESOURCE_KINDS,
        subject_refs=("entity:filtered",) if filtered else (),
        as_of=now,
        available_at=now,
        page_size=200,
    )
    evaluated_at = now + timedelta(seconds=1)
    authority = AuthorityUseReceiptV1Alpha1(
        product_id=projection.product_id,
        actor_ref=context.actor_ref,
        authenticated_context=context,
        use_subject_ref=str(query.query_id),
        use_subject_digest=str(query.query_digest),
        operation="query_intelligence_resources",
        authority="observe_read",
        grant_ref=query.authority_grant_ref,
        grant_hash="c" * 64,
        evaluated_at=evaluated_at,
        expires_at=now + timedelta(minutes=20),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
            state_kind="authority_grant",
            product_id=projection.product_id,
            state_id=query.authority_grant_ref,
            sequence=1,
            revision_id="authority_revision:resource-read",
            commit_receipt_id="authority_receipt:resource-read",
        ),
    )
    page = IntelligenceResourcePageV1Alpha1(
        query_id=str(query.query_id),
        query_digest=str(query.query_digest),
        product_id=projection.product_id,
        actor_ref=context.actor_ref,
        as_of=query.as_of,
        available_at=query.available_at,
        evaluated_at=evaluated_at,
        state=IntelligenceResourcePageState.DEGRADED if degraded else IntelligenceResourcePageState.COMPLETE,
        items=tuple(
            sorted(
                records,
                key=lambda item: (
                    item.reference.available_at,
                    item.reference.resource_kind.value,
                    item.reference.resource_id,
                    item.reference.revision,
                ),
            )
        ),
        degraded_reason_refs=("degraded_reason:resource-read",) if degraded else (),
        authority_use=authority,
    )
    return query, page


async def _projection_with_runtime_records():
    prepared, _ = await _request(planner=_Planner())
    plan = IntelligenceBuildPlanV1Alpha3.model_validate_json(prepared.content)
    projection = project_intelligence_system_plan(plan=plan, profile=PROFILE, pack=PACK)
    binding = projection.source_bindings[0]
    now = plan.request.requested_at + timedelta(minutes=10)
    module = PACK.modules[0]
    observation = ObservationV1Alpha1(
        product_id=projection.product_id,
        mode=IntelligenceResourceMode.LIVE,
        activation_revision=_activation(projection.product_id),
        as_of=now - timedelta(minutes=3),
        source_ref=binding.source_definition_ref,
        source_digest="sha256:" + "d" * 64,
        acquisition_mode=EvidenceAcquisitionMode.LIVE,
        acquisition_receipt_ref="source_acquisition:domain-health",
        acquisition_receipt_digest="sha256:" + "e" * 64,
        observed_at=now - timedelta(minutes=3),
        ingested_at=now - timedelta(minutes=2),
        subject_refs=(binding.entity_ref,),
        payload=CanonicalJsonValueV1Alpha1(value_json='{"measurement":42}'),
        confidence=0.9,
        source_mapping=SourceMappingReferenceV1Alpha1(
            activation_revision=_activation(projection.product_id),
            compiled_pack_id=projection.pack.compiled_pack_id,
            pack_digest=projection.pack.pack_digest,
            module_id=module.module_id,
            module_digest=module.module_digest,
            mapping_id=binding.mapping_id,
            mapping_digest="sha256:" + "9" * 64,
        ),
    )
    entity = EntitySnapshotV1Alpha1(
        product_id=projection.product_id,
        mode=IntelligenceResourceMode.LIVE,
        activation_revision=_activation(projection.product_id),
        as_of=now - timedelta(minutes=2),
        lineage=(
            LineageReferenceV1Alpha1(
                resource_kind=LineageResourceKind.OBSERVATION,
                resource_id=str(observation.resource_id),
                resource_digest=str(observation.resource_digest),
                resource_as_of=observation.as_of,
                resource_available_at=observation.ingested_at,
            ),
        ),
        entity_ref=binding.entity_ref,
        entity_type_ref=binding.entity_type_id,
        attributes=CanonicalJsonValueV1Alpha1(value_json='{"measurement":42}'),
        projected_at=now - timedelta(minutes=1),
        confidence=0.9,
    )
    records = (
        _record(observation, IntelligenceResourceKind.OBSERVATION),
        _record(entity, IntelligenceResourceKind.ENTITY),
        _source_health_record(projection=projection, at=now - timedelta(minutes=1)),
    )
    return projection, records, now


@pytest.mark.asyncio
async def test_resource_state_projects_exact_coverage_and_literal_source_health_without_scores() -> None:
    projection, records, now = await _projection_with_runtime_records()
    query, page = _query_and_page(projection=projection, records=records, now=now)

    enriched = project_intelligence_system_resource_state(projection=projection, query=query, page=page)

    assert enriched.mode is projection.mode
    assert all(item.predicted.support is ProjectionSupport.UNSUPPORTED for item in enriched.coverage)
    entity_row = next(
        item
        for item in enriched.coverage
        if item.dimension is CoverageDimension.ENTITY
        and item.target_ref.endswith(f":{projection.source_bindings[0].entity_type_id}")
    )
    assert entity_row.observed.support is ProjectionSupport.OBSERVED
    assert entity_row.observed.value is not None
    assert entity_row.observed.value.parsed_value()["state"] == "observed"
    assert entity_row.observed.value.parsed_value()["source_binding_ids"] == [projection.source_bindings[0].binding_id]
    health = {item.dimension: item.value for item in enriched.domain_health}
    assert health[DomainHealthDimension.COVERAGE].support is ProjectionSupport.DERIVED
    source_health = health[DomainHealthDimension.SOURCE_HEALTH]
    assert source_health.support is ProjectionSupport.OBSERVED
    source_value = source_health.value.parsed_value()
    assert source_value["bindings"][0]["readiness_state"] == "ready"
    assert source_value["bindings"][0]["freshness_verified"] is False
    assert all(
        health[dimension].support is ProjectionSupport.UNSUPPORTED
        for dimension in (
            DomainHealthDimension.FRESHNESS,
            DomainHealthDimension.CONFIDENCE,
            DomainHealthDimension.CONFLICTS,
            DomainHealthDimension.RESOLUTION,
            DomainHealthDimension.MAINTENANCE_HEALTH,
            DomainHealthDimension.HISTORICAL_DEPTH,
        )
    )
    serialized = enriched.model_dump_json()
    assert '"score"' not in serialized
    assert '"percentage"' not in serialized
    assert enriched.projection_digest != projection.projection_digest
    assert enriched.generated_at == page.evaluated_at


@pytest.mark.asyncio
@pytest.mark.parametrize("degraded,filtered", [(True, False), (False, True)])
async def test_resource_state_fails_closed_for_partial_domain_reads(degraded: bool, filtered: bool) -> None:
    projection, records, now = await _projection_with_runtime_records()
    query, page = _query_and_page(
        projection=projection,
        records=records,
        now=now,
        degraded=degraded,
        filtered=filtered,
    )

    enriched = project_intelligence_system_resource_state(projection=projection, query=query, page=page)

    assert all(item.observed.support is ProjectionSupport.UNSUPPORTED for item in enriched.coverage)
    health = {item.dimension: item.value for item in enriched.domain_health}
    assert health[DomainHealthDimension.COVERAGE].support is ProjectionSupport.UNSUPPORTED
    assert health[DomainHealthDimension.SOURCE_HEALTH].support is ProjectionSupport.UNSUPPORTED


@pytest.mark.asyncio
async def test_resource_state_rejects_crossed_query_identity() -> None:
    projection, records, now = await _projection_with_runtime_records()
    query, page = _query_and_page(projection=projection, records=records, now=now)
    foreign_query = query.model_copy(update={"product_id": "product:foreign"})

    with pytest.raises(ValueError):
        project_intelligence_system_resource_state(
            projection=projection,
            query=foreign_query,
            page=page,
        )


@pytest.mark.asyncio
async def test_resource_state_promotes_to_live_mode_with_exact_activation_association() -> None:
    projection, records, now = await _projection_with_runtime_records()
    query, page = _query_and_page(projection=projection, records=records, now=now)
    activation_revision = _activation(projection.product_id)

    enriched = project_intelligence_system_resource_state(
        projection=projection,
        query=query,
        page=page,
        activation_revision=activation_revision,
    )

    assert enriched.mode is ProjectionMode.LIVE
    assert enriched.activation_revision == activation_revision
    entity_row = next(
        item
        for item in enriched.coverage
        if item.dimension is CoverageDimension.ENTITY
        and item.target_ref.endswith(f":{projection.source_bindings[0].entity_type_id}")
    )
    assert entity_row.observed.value.parsed_value()["state"] == "observed"


@pytest.mark.asyncio
async def test_resource_state_excludes_resources_bound_to_a_different_activation_revision() -> None:
    projection, records, now = await _projection_with_runtime_records()
    query, page = _query_and_page(projection=projection, records=records, now=now)
    other_activation = _activation(projection.product_id, digest_char="b")

    enriched = project_intelligence_system_resource_state(
        projection=projection,
        query=query,
        page=page,
        activation_revision=other_activation,
    )

    # The accepted-session association itself is still exact and current, so
    # the projection honestly reports "live" — but no resource is counted as
    # observed evidence for an activation revision it was not produced under.
    assert enriched.mode is ProjectionMode.LIVE
    entity_row = next(
        item
        for item in enriched.coverage
        if item.dimension is CoverageDimension.ENTITY
        and item.target_ref.endswith(f":{projection.source_bindings[0].entity_type_id}")
    )
    assert entity_row.observed.value.parsed_value()["state"] == "not_observed"


@pytest.mark.asyncio
async def test_resource_state_rejects_crossed_product_activation_revision() -> None:
    projection, records, now = await _projection_with_runtime_records()
    query, page = _query_and_page(projection=projection, records=records, now=now)
    foreign_activation = _activation("product:foreign")

    with pytest.raises(ValueError):
        project_intelligence_system_resource_state(
            projection=projection,
            query=query,
            page=page,
            activation_revision=foreign_activation,
        )


@pytest.mark.asyncio
async def test_resource_state_stays_in_input_mode_when_association_present_but_page_not_closed() -> None:
    projection, records, now = await _projection_with_runtime_records()
    query, page = _query_and_page(projection=projection, records=records, now=now, degraded=True)
    activation_revision = _activation(projection.product_id)

    enriched = project_intelligence_system_resource_state(
        projection=projection,
        query=query,
        page=page,
        activation_revision=activation_revision,
    )

    assert enriched.mode is projection.mode
    assert enriched.activation_revision is None
    assert any("did not fully close" in gap for gap in enriched.gaps)
