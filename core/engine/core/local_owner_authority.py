"""Create-or-verify authority for the fixed single-user ACE owner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ace.application.intelligence_resource_feedback import RESOURCE_FEEDBACK_OPERATION
from ace.application.intelligence_resource_plane import RESOURCE_QUERY_OPERATION
from ace.application.recorded_source_admission import INTELLIGENCE_BUILD_OPERATION
from ace.core.agent_composition import AuthorityClass
from ace.core.contracts import canonical_hash
from ace.core.reasoning import (
    GOVERNED_OPERATION_CONFIGURATION_STATE_KIND,
    REASONING_CONFIGURATION_STATE_KIND,
)
from ace.core.runtime_use import CAPABILITY_STATE_KIND, capability_state_ref_for_artifact
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateHeadV1,
    GovernedStateRevisionV1,
    GovernedStateStore,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from core.engine.core.agent_composition_runtime import (
    CAPABILITY_PAYLOAD_CONTRACT,
    CONFIGURATION_PAYLOAD_CONTRACT,
    GRANT_PAYLOAD_CONTRACT,
    CompositionAuthorityGrantMaterial,
    CompositionCapabilityStateMaterial,
    ReasoningCompositionConfigurationMaterial,
)
from core.engine.core.governed_state import GovernedStateHeadConflict
from core.engine.core.intelligence_build_cognition import (
    APPEND_ARTIFACT,
    APPEND_RECORDS_OPERATION,
    FIRST_BRIEF_APPEND_CONFIGURATION_REF,
    FIRST_BRIEF_REASONING_CONFIGURATION_REF,
    INTELLIGENCE_BUILD_APPEND_CONFIGURATION_PAYLOAD_CONTRACT,
    REASONING_ADAPTER_ARTIFACT,
    REASONING_GRANT_OPERATION,
    IntelligenceBuildAppendConfigurationMaterial,
)
from core.engine.core.personal_intelligence_ownership import (
    CONFIRM_DELETE_OPERATION,
    EXPORT_OPERATION,
    PREVIEW_DELETE_OPERATION,
)

LOCAL_OWNER_ACTOR_REF = "user:default"
LOCAL_OWNER_PRODUCT_ID = "product:platform"
LOCAL_OWNER_POLICY_REF = "authority_policy:single-user-owner-v1"


@dataclass(frozen=True, slots=True)
class LocalOwnerGrantSpec:
    grant_ref: str
    authority_class: AuthorityClass
    operations: tuple[str, ...]


LOCAL_OWNER_GRANTS = (
    LocalOwnerGrantSpec(
        grant_ref="authority_grant:atrium-intelligence-build",
        authority_class=AuthorityClass.INTELLIGENCE_BUILD,
        operations=(INTELLIGENCE_BUILD_OPERATION,),
    ),
    LocalOwnerGrantSpec(
        grant_ref="authority_grant:atrium-observe-read",
        authority_class=AuthorityClass.OBSERVE_READ,
        operations=(RESOURCE_QUERY_OPERATION,),
    ),
    LocalOwnerGrantSpec(
        grant_ref="authority_grant:atrium-resource-feedback",
        authority_class=AuthorityClass.DERIVE_PROPOSE,
        operations=(RESOURCE_FEEDBACK_OPERATION, REASONING_GRANT_OPERATION, APPEND_RECORDS_OPERATION),
    ),
    LocalOwnerGrantSpec(
        grant_ref="authority_grant:personal-export",
        authority_class=AuthorityClass.DELIVER_EXPORT,
        operations=(EXPORT_OPERATION,),
    ),
    LocalOwnerGrantSpec(
        grant_ref="authority_grant:personal-delete",
        authority_class=AuthorityClass.ADMINISTER_LIFECYCLE,
        operations=(PREVIEW_DELETE_OPERATION, CONFIRM_DELETE_OPERATION),
    ),
)

# The feedback grant originally carried only its singleton operation. A prior
# durable grant material must migrate exactly, so its expected shape is kept
# private here for exact lineage comparison.
_LEGACY_FEEDBACK_GRANT_SPEC = LocalOwnerGrantSpec(
    grant_ref="authority_grant:atrium-resource-feedback",
    authority_class=AuthorityClass.DERIVE_PROPOSE,
    operations=(RESOURCE_FEEDBACK_OPERATION,),
)


@dataclass(frozen=True, slots=True)
class LocalOwnerCognitionSpec:
    state_kind: str
    state_id: str
    payload_contract: str
    material: BaseModel


_REASONING_CAPABILITY_STATE = CompositionCapabilityStateMaterial(
    contract=CAPABILITY_PAYLOAD_CONTRACT,
    product_id=LOCAL_OWNER_PRODUCT_ID,
    artifact=REASONING_ADAPTER_ARTIFACT,
    lifecycle="active",
    permitted_configuration_refs=(FIRST_BRIEF_REASONING_CONFIGURATION_REF,),
)

_APPEND_CAPABILITY_STATE = CompositionCapabilityStateMaterial(
    contract=CAPABILITY_PAYLOAD_CONTRACT,
    product_id=LOCAL_OWNER_PRODUCT_ID,
    artifact=APPEND_ARTIFACT,
    lifecycle="active",
    permitted_configuration_refs=(FIRST_BRIEF_APPEND_CONFIGURATION_REF,),
)

_REASONING_CONFIGURATION = ReasoningCompositionConfigurationMaterial(
    contract=CONFIGURATION_PAYLOAD_CONTRACT,
    product_id=LOCAL_OWNER_PRODUCT_ID,
    configuration_ref=FIRST_BRIEF_REASONING_CONFIGURATION_REF,
    artifact=REASONING_ADAPTER_ARTIFACT,
    authority=AuthorityClass.DERIVE_PROPOSE,
    grant_ref="authority_grant:atrium-resource-feedback",
    lifecycle="active",
)

_APPEND_CONFIGURATION = IntelligenceBuildAppendConfigurationMaterial(
    contract=INTELLIGENCE_BUILD_APPEND_CONFIGURATION_PAYLOAD_CONTRACT,
    product_id=LOCAL_OWNER_PRODUCT_ID,
    configuration_ref=FIRST_BRIEF_APPEND_CONFIGURATION_REF,
    artifact=APPEND_ARTIFACT,
    authority=AuthorityClass.DERIVE_PROPOSE.value,
    grant_ref="authority_grant:atrium-resource-feedback",
    operation=APPEND_RECORDS_OPERATION,
    lifecycle="active",
)

LOCAL_OWNER_COGNITION = (
    LocalOwnerCognitionSpec(
        state_kind=CAPABILITY_STATE_KIND,
        state_id=capability_state_ref_for_artifact(REASONING_ADAPTER_ARTIFACT),
        payload_contract=CAPABILITY_PAYLOAD_CONTRACT,
        material=_REASONING_CAPABILITY_STATE,
    ),
    LocalOwnerCognitionSpec(
        state_kind=CAPABILITY_STATE_KIND,
        state_id=capability_state_ref_for_artifact(APPEND_ARTIFACT),
        payload_contract=CAPABILITY_PAYLOAD_CONTRACT,
        material=_APPEND_CAPABILITY_STATE,
    ),
    LocalOwnerCognitionSpec(
        state_kind=REASONING_CONFIGURATION_STATE_KIND,
        state_id=FIRST_BRIEF_REASONING_CONFIGURATION_REF,
        payload_contract=CONFIGURATION_PAYLOAD_CONTRACT,
        material=_REASONING_CONFIGURATION,
    ),
    LocalOwnerCognitionSpec(
        state_kind=GOVERNED_OPERATION_CONFIGURATION_STATE_KIND,
        state_id=FIRST_BRIEF_APPEND_CONFIGURATION_REF,
        payload_contract=INTELLIGENCE_BUILD_APPEND_CONFIGURATION_PAYLOAD_CONTRACT,
        material=_APPEND_CONFIGURATION,
    ),
)


class LocalOwnerAuthorityError(RuntimeError):
    """The local-owner authority bootstrap could not complete safely."""


class LocalOwnerAuthorityDenied(LocalOwnerAuthorityError):
    """The signed caller is not the fixed local owner."""


class LocalOwnerAuthorityConflict(LocalOwnerAuthorityError):
    """An existing fixed grant differs from the approved bootstrap material."""


class LocalOwnerGrantStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grant_ref: str
    status: Literal["created", "verified", "migrated"]


class LocalOwnerCognitionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state_kind: str
    state_id: str
    status: Literal["created", "verified"]


class LocalOwnerAuthorityBootstrapResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: str
    actor_ref: str
    grants: tuple[LocalOwnerGrantStatus, ...]
    cognition: tuple[LocalOwnerCognitionStatus, ...]


def _grant_material(
    spec: LocalOwnerGrantSpec,
    *,
    effective_at: datetime,
) -> CompositionAuthorityGrantMaterial:
    material = {
        "contract": GRANT_PAYLOAD_CONTRACT,
        "grant_ref": spec.grant_ref,
        "product_id": LOCAL_OWNER_PRODUCT_ID,
        "actor_ref": LOCAL_OWNER_ACTOR_REF,
        "participant_principal_ref": LOCAL_OWNER_ACTOR_REF,
        "delegator_ref": None,
        "authority_class": spec.authority_class,
        "operations": tuple(sorted(spec.operations)),
        "scope_ref": LOCAL_OWNER_PRODUCT_ID,
        "policy_ref": LOCAL_OWNER_POLICY_REF,
        "lifecycle": "active",
        "effective_at": effective_at,
        "expires_at": None,
        "revoked_at": None,
        "delegation_ceiling": (),
    }
    provisional = CompositionAuthorityGrantMaterial(**material, grant_hash="0" * 64)
    grant_hash = canonical_hash(provisional.model_dump(mode="json", exclude={"grant_hash"}))
    return CompositionAuthorityGrantMaterial(**material, grant_hash=grant_hash)


@dataclass(frozen=True, slots=True)
class _GrantLineage:
    status: Literal["absent", "current", "legacy"]
    head: GovernedStateHeadV1 | None = None
    grant: CompositionAuthorityGrantMaterial | None = None


async def _load_grant_lineage(store: GovernedStateStore, spec: LocalOwnerGrantSpec) -> _GrantLineage:
    """Classify one fixed grant's durable lineage as absent, current, or legacy."""

    head = await store.load_head(
        state_kind="authority_grant",
        product_id=LOCAL_OWNER_PRODUCT_ID,
        state_id=spec.grant_ref,
    )
    if head is None:
        return _GrantLineage(status="absent")
    revision = await store.load_revision(head.revision_id, product_id=LOCAL_OWNER_PRODUCT_ID)
    receipt = await store.load_receipt(head.commit_receipt_id, product_id=LOCAL_OWNER_PRODUCT_ID)
    is_feedback = spec.grant_ref == _LEGACY_FEEDBACK_GRANT_SPEC.grant_ref
    if (
        revision is None
        or receipt is None
        or head.state_kind != "authority_grant"
        or head.product_id != LOCAL_OWNER_PRODUCT_ID
        or head.state_id != spec.grant_ref
        or head.sequence != revision.sequence
        or head.revision_id != revision.revision_id
        or receipt.state_kind != revision.state_kind
        or receipt.product_id != revision.product_id
        or receipt.state_id != revision.state_id
        or receipt.sequence != revision.sequence
        or receipt.revision_id != revision.revision_id
        or receipt.prior_revision_id != revision.prior_revision_id
        or receipt.material_hash != revision.material_hash
        or receipt.receipt_id != head.commit_receipt_id
        or receipt.product_id != LOCAL_OWNER_PRODUCT_ID
        or receipt.actor_ref != LOCAL_OWNER_ACTOR_REF
        or receipt.approval.product_id != revision.product_id
        or receipt.approval.subject_ref != revision.approval_subject_ref
        or receipt.approval.actor_ref != receipt.actor_ref
        or len(receipt.authority_grants) != 1
        or revision.state_kind != "authority_grant"
        or revision.product_id != LOCAL_OWNER_PRODUCT_ID
        or revision.state_id != spec.grant_ref
        or revision.payload_contract != GRANT_PAYLOAD_CONTRACT
        or (not is_feedback and (revision.sequence != 1 or revision.prior_revision_id is not None))
        or (is_feedback and revision.sequence not in (1, 2))
        or (is_feedback and revision.sequence == 1 and revision.prior_revision_id is not None)
        or (is_feedback and revision.sequence == 2 and revision.prior_revision_id is None)
    ):
        raise LocalOwnerAuthorityConflict(f"fixed grant lineage is incomplete: {spec.grant_ref}")
    expected_receipt_ref_prefix = (
        "approval:local-owner-migration:"
        if (is_feedback and revision.sequence == 2)
        else "approval:local-owner-bootstrap:"
    )
    expected_approval_subject_ref = f"approval_subject:local-owner:{spec.grant_ref.rsplit(':', 1)[-1]}"
    if is_feedback and revision.sequence == 2:
        expected_approval_subject_ref = f"{expected_approval_subject_ref}:migration"
    approval_hash = canonical_hash(
        {
            "actor_ref": LOCAL_OWNER_ACTOR_REF,
            "product_id": LOCAL_OWNER_PRODUCT_ID,
            "subject_ref": revision.approval_subject_ref,
            "approved_at": receipt.approval.approved_at.isoformat(),
        }
    )
    if (
        head.updated_at != receipt.committed_at
        or receipt.approval.approved_at != receipt.committed_at
        or revision.approval_subject_ref != expected_approval_subject_ref
        or revision.revision_id != f"authority_grant_revision:{revision.material_hash[:32]}"
        or receipt.approval.receipt_hash != approval_hash
        or receipt.approval.receipt_ref != f"{expected_receipt_ref_prefix}{approval_hash[:32]}"
    ):
        raise LocalOwnerAuthorityConflict(f"fixed grant lineage is incomplete: {spec.grant_ref}")
    try:
        # SurrealDB returns JSON-shaped material: tuples become lists, enums become
        # strings, and datetimes may be decoded from their wire representation.  The
        # private grant contract is strict for newly constructed Python material, but
        # a durable JSON round trip must be accepted before the exact hash, expected
        # material, and receipt comparisons below fail closed on any real change.
        grant = CompositionAuthorityGrantMaterial.model_validate(revision.payload, strict=False)
    except ValueError as exc:
        raise LocalOwnerAuthorityConflict(f"fixed grant is malformed: {spec.grant_ref}") from exc
    if revision.material_hash != canonical_hash(grant.model_dump(mode="json")):
        raise LocalOwnerAuthorityConflict(f"fixed grant lineage is incomplete: {spec.grant_ref}")
    resolved = receipt.authority_grants[0]

    def _matches(expected: CompositionAuthorityGrantMaterial) -> bool:
        return grant == expected and (
            resolved.grant_ref == expected.grant_ref
            and resolved.product_id == expected.product_id
            and resolved.authority == expected.authority_class.value
            and resolved.grant_hash == expected.grant_hash
            and resolved.effective_at == expected.effective_at
            and resolved.expires_at == expected.expires_at
            and resolved.state == "active"
        )

    if (
        revision.sequence == 1
        and revision.prior_revision_id is None
        and _matches(_grant_material(spec, effective_at=grant.effective_at))
    ):
        return _GrantLineage(status="current", head=head, grant=grant)

    if (
        is_feedback
        and revision.sequence == 2
        and revision.prior_revision_id is not None
        and _matches(_grant_material(spec, effective_at=grant.effective_at))
    ):
        legacy_material = _grant_material(_LEGACY_FEEDBACK_GRANT_SPEC, effective_at=grant.effective_at)
        legacy_material_hash = canonical_hash(legacy_material.model_dump(mode="json"))
        expected_legacy_revision_id = f"authority_grant_revision:{legacy_material_hash[:32]}"
        # The store protocol has no port for a historical receipt, so a migrated
        # head's legacy prior revision is verified directly and exactly instead.
        historical = await store.load_revision(revision.prior_revision_id, product_id=LOCAL_OWNER_PRODUCT_ID)
        try:
            historical_grant = (
                CompositionAuthorityGrantMaterial.model_validate(historical.payload, strict=False)
                if historical is not None
                else None
            )
        except ValueError as exc:
            raise LocalOwnerAuthorityConflict(f"fixed grant lineage is incomplete: {spec.grant_ref}") from exc
        if (
            revision.prior_revision_id != expected_legacy_revision_id
            or historical is None
            or historical.state_kind != "authority_grant"
            or historical.product_id != LOCAL_OWNER_PRODUCT_ID
            or historical.state_id != spec.grant_ref
            or historical.payload_contract != GRANT_PAYLOAD_CONTRACT
            or historical.sequence != 1
            or historical.prior_revision_id is not None
            or historical.material_hash != legacy_material_hash
            or historical_grant != legacy_material
            or canonical_hash(historical_grant.model_dump(mode="json")) != historical.material_hash
        ):
            raise LocalOwnerAuthorityConflict(f"fixed grant lineage is incomplete: {spec.grant_ref}")
        return _GrantLineage(status="current", head=head, grant=grant)

    if (
        is_feedback
        and revision.sequence == 1
        and revision.prior_revision_id is None
        and receipt.prior_revision_id is None
        and _matches(_grant_material(_LEGACY_FEEDBACK_GRANT_SPEC, effective_at=grant.effective_at))
    ):
        return _GrantLineage(status="legacy", head=head, grant=grant)

    raise LocalOwnerAuthorityConflict(f"fixed grant differs from approved material: {spec.grant_ref}")


async def _create_grant(
    store: GovernedStateStore,
    spec: LocalOwnerGrantSpec,
    *,
    approved_at: datetime,
) -> Literal["created", "verified"]:
    grant = _grant_material(spec, effective_at=approved_at)
    payload = grant.model_dump(mode="python")
    material_hash = canonical_hash(grant.model_dump(mode="json"))
    approval_subject_ref = f"approval_subject:local-owner:{spec.grant_ref.rsplit(':', 1)[-1]}"
    revision = GovernedStateRevisionV1(
        state_kind="authority_grant",
        product_id=LOCAL_OWNER_PRODUCT_ID,
        state_id=spec.grant_ref,
        sequence=1,
        revision_id=f"authority_grant_revision:{material_hash[:32]}",
        material_hash=material_hash,
        approval_subject_ref=approval_subject_ref,
        payload_contract=GRANT_PAYLOAD_CONTRACT,
        payload=payload,
    )
    approval_hash = canonical_hash(
        {
            "actor_ref": LOCAL_OWNER_ACTOR_REF,
            "product_id": LOCAL_OWNER_PRODUCT_ID,
            "subject_ref": approval_subject_ref,
            "approved_at": approved_at.isoformat(),
        }
    )
    request = GovernedStateCommitRequestV1(
        revision=revision,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        approval=ResolvedApprovalReceiptV1(
            receipt_ref=f"approval:local-owner-bootstrap:{approval_hash[:32]}",
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=approval_subject_ref,
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            receipt_hash=approval_hash,
            approved_at=approved_at,
        ),
        authority_grants=(
            ResolvedAuthorityGrantV1(
                grant_ref=grant.grant_ref,
                product_id=grant.product_id,
                authority=grant.authority_class.value,
                grant_hash=grant.grant_hash,
                effective_at=grant.effective_at,
                expires_at=grant.expires_at,
            ),
        ),
        committed_at=approved_at,
    )
    try:
        await store.commit(request)
    except GovernedStateHeadConflict:
        lineage = await _load_grant_lineage(store, spec)
        if lineage.status == "current":
            return "verified"
        raise
    return "created"


async def _migrate_legacy_grant(
    store: GovernedStateStore,
    spec: LocalOwnerGrantSpec,
    *,
    head: GovernedStateHeadV1,
    legacy_grant: CompositionAuthorityGrantMaterial,
    approved_at: datetime,
) -> Literal["migrated", "verified"]:
    widened = _grant_material(spec, effective_at=legacy_grant.effective_at)
    payload = widened.model_dump(mode="python")
    material_hash = canonical_hash(widened.model_dump(mode="json"))
    approval_subject_ref = f"approval_subject:local-owner:{spec.grant_ref.rsplit(':', 1)[-1]}:migration"
    revision = GovernedStateRevisionV1(
        state_kind="authority_grant",
        product_id=LOCAL_OWNER_PRODUCT_ID,
        state_id=spec.grant_ref,
        sequence=head.sequence + 1,
        revision_id=f"authority_grant_revision:{material_hash[:32]}",
        material_hash=material_hash,
        prior_revision_id=head.revision_id,
        approval_subject_ref=approval_subject_ref,
        payload_contract=GRANT_PAYLOAD_CONTRACT,
        payload=payload,
    )
    approval_hash = canonical_hash(
        {
            "actor_ref": LOCAL_OWNER_ACTOR_REF,
            "product_id": LOCAL_OWNER_PRODUCT_ID,
            "subject_ref": approval_subject_ref,
            "approved_at": approved_at.isoformat(),
        }
    )
    request = GovernedStateCommitRequestV1(
        revision=revision,
        expected_head_revision_id=head.revision_id,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        approval=ResolvedApprovalReceiptV1(
            receipt_ref=f"approval:local-owner-migration:{approval_hash[:32]}",
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=approval_subject_ref,
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            receipt_hash=approval_hash,
            approved_at=approved_at,
        ),
        authority_grants=(
            ResolvedAuthorityGrantV1(
                grant_ref=widened.grant_ref,
                product_id=widened.product_id,
                authority=widened.authority_class.value,
                grant_hash=widened.grant_hash,
                effective_at=widened.effective_at,
                expires_at=widened.expires_at,
            ),
        ),
        committed_at=approved_at,
    )
    try:
        await store.commit(request)
    except GovernedStateHeadConflict:
        lineage = await _load_grant_lineage(store, spec)
        if lineage.status == "current":
            return "verified"
        raise
    return "migrated"


async def _verify_cognition_existing(store: GovernedStateStore, spec: LocalOwnerCognitionSpec) -> bool:
    head = await store.load_head(
        state_kind=spec.state_kind,
        product_id=LOCAL_OWNER_PRODUCT_ID,
        state_id=spec.state_id,
    )
    if head is None:
        return False
    revision = await store.load_revision(head.revision_id, product_id=LOCAL_OWNER_PRODUCT_ID)
    receipt = await store.load_receipt(head.commit_receipt_id, product_id=LOCAL_OWNER_PRODUCT_ID)
    if (
        revision is None
        or receipt is None
        or head.state_kind != spec.state_kind
        or head.product_id != LOCAL_OWNER_PRODUCT_ID
        or head.state_id != spec.state_id
        or head.sequence != revision.sequence
        or head.revision_id != revision.revision_id
        or receipt.state_kind != revision.state_kind
        or receipt.product_id != revision.product_id
        or receipt.state_id != revision.state_id
        or receipt.sequence != revision.sequence
        or receipt.revision_id != revision.revision_id
        or receipt.prior_revision_id != revision.prior_revision_id
        or receipt.material_hash != revision.material_hash
        or receipt.receipt_id != head.commit_receipt_id
        or receipt.product_id != LOCAL_OWNER_PRODUCT_ID
        or receipt.actor_ref != LOCAL_OWNER_ACTOR_REF
        or receipt.approval.product_id != revision.product_id
        or receipt.approval.subject_ref != revision.approval_subject_ref
        or receipt.approval.actor_ref != receipt.actor_ref
        or receipt.authority_grants != ()
        or revision.state_kind != spec.state_kind
        or revision.product_id != LOCAL_OWNER_PRODUCT_ID
        or revision.state_id != spec.state_id
        or revision.payload_contract != spec.payload_contract
        or revision.sequence != 1
        or revision.prior_revision_id is not None
    ):
        raise LocalOwnerAuthorityConflict(f"fixed cognition state lineage is incomplete: {spec.state_id}")
    approval_hash = canonical_hash(
        {
            "actor_ref": LOCAL_OWNER_ACTOR_REF,
            "product_id": LOCAL_OWNER_PRODUCT_ID,
            "subject_ref": revision.approval_subject_ref,
            "approved_at": receipt.approval.approved_at.isoformat(),
        }
    )
    if (
        head.updated_at != receipt.committed_at
        or receipt.approval.approved_at != receipt.committed_at
        or revision.approval_subject_ref != f"approval_subject:local-owner:{spec.state_id.rsplit(':', 1)[-1]}"
        or revision.revision_id != f"{spec.state_kind}_revision:{revision.material_hash[:32]}"
        or receipt.approval.receipt_hash != approval_hash
        or receipt.approval.receipt_ref != f"approval:local-owner-bootstrap:{approval_hash[:32]}"
    ):
        raise LocalOwnerAuthorityConflict(f"fixed cognition state lineage is incomplete: {spec.state_id}")
    try:
        # See _load_grant_lineage: durable stores return JSON-shaped material, so
        # the private state contract must accept the wire representation before
        # the exact hash and material comparisons below fail closed.
        material = type(spec.material).model_validate(revision.payload, strict=False)
    except ValueError as exc:
        raise LocalOwnerAuthorityConflict(f"fixed cognition state is malformed: {spec.state_id}") from exc
    if material != spec.material or revision.material_hash != canonical_hash(material.model_dump(mode="json")):
        raise LocalOwnerAuthorityConflict(f"fixed cognition state differs from approved material: {spec.state_id}")
    return True


async def _create_cognition(
    store: GovernedStateStore,
    spec: LocalOwnerCognitionSpec,
    *,
    approved_at: datetime,
) -> Literal["created", "verified"]:
    payload = spec.material.model_dump(mode="python")
    material_hash = canonical_hash(spec.material.model_dump(mode="json"))
    approval_subject_ref = f"approval_subject:local-owner:{spec.state_id.rsplit(':', 1)[-1]}"
    revision = GovernedStateRevisionV1(
        state_kind=spec.state_kind,
        product_id=LOCAL_OWNER_PRODUCT_ID,
        state_id=spec.state_id,
        sequence=1,
        revision_id=f"{spec.state_kind}_revision:{material_hash[:32]}",
        material_hash=material_hash,
        approval_subject_ref=approval_subject_ref,
        payload_contract=spec.payload_contract,
        payload=payload,
    )
    approval_hash = canonical_hash(
        {
            "actor_ref": LOCAL_OWNER_ACTOR_REF,
            "product_id": LOCAL_OWNER_PRODUCT_ID,
            "subject_ref": approval_subject_ref,
            "approved_at": approved_at.isoformat(),
        }
    )
    request = GovernedStateCommitRequestV1(
        revision=revision,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        approval=ResolvedApprovalReceiptV1(
            receipt_ref=f"approval:local-owner-bootstrap:{approval_hash[:32]}",
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=approval_subject_ref,
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            receipt_hash=approval_hash,
            approved_at=approved_at,
        ),
        authority_grants=(),
        committed_at=approved_at,
    )
    try:
        await store.commit(request)
    except GovernedStateHeadConflict:
        if await _verify_cognition_existing(store, spec):
            return "verified"
        raise
    return "created"


async def bootstrap_local_owner_authority(
    *,
    user: dict,
    store: GovernedStateStore,
    approved_at: datetime | None = None,
) -> LocalOwnerAuthorityBootstrapResult:
    """Create missing fixed grants and verify every pre-existing grant exactly."""

    authorities = user.get("authorities")
    if (
        user.get("local_owner") is not True
        or user.get("sub") != LOCAL_OWNER_ACTOR_REF
        or user.get("product") != LOCAL_OWNER_PRODUCT_ID
        or not isinstance(authorities, list)
    ):
        raise LocalOwnerAuthorityDenied("signed token is not the fixed local owner")
    expected_authorities = {
        "cognition-review",
        *(spec.authority_class.value for spec in LOCAL_OWNER_GRANTS),
    }
    if set(authorities) != expected_authorities:
        raise LocalOwnerAuthorityDenied("local-owner token authority set is not exact")

    now = (approved_at or datetime.now(UTC)).astimezone(UTC)
    # Preflight every grant and every cognition head before creating, migrating,
    # or committing anything. This prevents a mismatch or revocation from being
    # partially papered over by setup.
    lineages = [await _load_grant_lineage(store, spec) for spec in LOCAL_OWNER_GRANTS]
    cognition_existing = [await _verify_cognition_existing(store, spec) for spec in LOCAL_OWNER_COGNITION]

    grant_statuses: list[LocalOwnerGrantStatus] = []
    for spec, lineage in zip(LOCAL_OWNER_GRANTS, lineages, strict=True):
        status: Literal["created", "verified", "migrated"]
        if lineage.status == "current":
            status = "verified"
        elif lineage.status == "legacy":
            assert lineage.head is not None and lineage.grant is not None
            status = await _migrate_legacy_grant(
                store,
                spec,
                head=lineage.head,
                legacy_grant=lineage.grant,
                approved_at=now,
            )
        else:
            status = await _create_grant(store, spec, approved_at=now)
        grant_statuses.append(LocalOwnerGrantStatus(grant_ref=spec.grant_ref, status=status))

    cognition_statuses: list[LocalOwnerCognitionStatus] = []
    for spec, exists in zip(LOCAL_OWNER_COGNITION, cognition_existing, strict=True):
        cognition_status: Literal["created", "verified"]
        cognition_status = "verified" if exists else await _create_cognition(store, spec, approved_at=now)
        cognition_statuses.append(
            LocalOwnerCognitionStatus(
                state_kind=spec.state_kind,
                state_id=spec.state_id,
                status=cognition_status,
            )
        )

    return LocalOwnerAuthorityBootstrapResult(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        grants=tuple(grant_statuses),
        cognition=tuple(cognition_statuses),
    )


__all__ = [
    "LOCAL_OWNER_ACTOR_REF",
    "LOCAL_OWNER_COGNITION",
    "LOCAL_OWNER_GRANTS",
    "LOCAL_OWNER_POLICY_REF",
    "LOCAL_OWNER_PRODUCT_ID",
    "LocalOwnerAuthorityBootstrapResult",
    "LocalOwnerAuthorityConflict",
    "LocalOwnerAuthorityDenied",
    "LocalOwnerAuthorityError",
    "LocalOwnerCognitionSpec",
    "LocalOwnerCognitionStatus",
    "LocalOwnerGrantSpec",
    "LocalOwnerGrantStatus",
    "bootstrap_local_owner_authority",
]
