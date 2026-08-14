"""Create-or-verify authority for the fixed single-user ACE owner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ace.application.intelligence_resource_plane import RESOURCE_QUERY_OPERATION
from ace.application.recorded_source_admission import INTELLIGENCE_BUILD_OPERATION
from ace.core.agent_composition import AuthorityClass
from ace.core.contracts import canonical_hash
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateRevisionV1,
    GovernedStateStore,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from core.engine.core.agent_composition_runtime import (
    GRANT_PAYLOAD_CONTRACT,
    CompositionAuthorityGrantMaterial,
)
from core.engine.core.governed_state import GovernedStateHeadConflict
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


class LocalOwnerAuthorityError(RuntimeError):
    """The local-owner authority bootstrap could not complete safely."""


class LocalOwnerAuthorityDenied(LocalOwnerAuthorityError):
    """The signed caller is not the fixed local owner."""


class LocalOwnerAuthorityConflict(LocalOwnerAuthorityError):
    """An existing fixed grant differs from the approved bootstrap material."""


class LocalOwnerGrantStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grant_ref: str
    status: Literal["created", "verified"]


class LocalOwnerAuthorityBootstrapResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: str
    actor_ref: str
    grants: tuple[LocalOwnerGrantStatus, ...]


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


def _validate_existing(
    spec: LocalOwnerGrantSpec,
    *,
    revision: GovernedStateRevisionV1,
) -> None:
    try:
        grant = CompositionAuthorityGrantMaterial.model_validate(revision.payload)
    except ValueError as exc:
        raise LocalOwnerAuthorityConflict(f"fixed grant is malformed: {spec.grant_ref}") from exc
    expected = _grant_material(spec, effective_at=grant.effective_at)
    if (
        revision.state_kind != "authority_grant"
        or revision.product_id != LOCAL_OWNER_PRODUCT_ID
        or revision.state_id != spec.grant_ref
        or revision.payload_contract != GRANT_PAYLOAD_CONTRACT
        or revision.material_hash != canonical_hash(grant.model_dump(mode="json"))
        or grant != expected
    ):
        raise LocalOwnerAuthorityConflict(f"fixed grant differs from approved material: {spec.grant_ref}")


async def _verify_existing(store: GovernedStateStore, spec: LocalOwnerGrantSpec) -> bool:
    head = await store.load_head(
        state_kind="authority_grant",
        product_id=LOCAL_OWNER_PRODUCT_ID,
        state_id=spec.grant_ref,
    )
    if head is None:
        return False
    revision = await store.load_revision(head.revision_id, product_id=LOCAL_OWNER_PRODUCT_ID)
    receipt = await store.load_receipt(head.commit_receipt_id, product_id=LOCAL_OWNER_PRODUCT_ID)
    if (
        revision is None
        or receipt is None
        or head.sequence != revision.sequence
        or head.revision_id != revision.revision_id
        or receipt.revision_id != revision.revision_id
        or receipt.receipt_id != head.commit_receipt_id
        or receipt.material_hash != revision.material_hash
        or receipt.product_id != LOCAL_OWNER_PRODUCT_ID
        or receipt.actor_ref != LOCAL_OWNER_ACTOR_REF
        or len(receipt.authority_grants) != 1
    ):
        raise LocalOwnerAuthorityConflict(f"fixed grant lineage is incomplete: {spec.grant_ref}")
    _validate_existing(spec, revision=revision)
    grant = CompositionAuthorityGrantMaterial.model_validate(revision.payload)
    resolved = receipt.authority_grants[0]
    if (
        resolved.grant_ref != grant.grant_ref
        or resolved.product_id != grant.product_id
        or resolved.authority != grant.authority_class.value
        or resolved.grant_hash != grant.grant_hash
        or resolved.effective_at != grant.effective_at
        or resolved.expires_at != grant.expires_at
    ):
        raise LocalOwnerAuthorityConflict(f"fixed grant receipt differs from its material: {spec.grant_ref}")
    return True


async def _create_or_verify(
    store: GovernedStateStore,
    spec: LocalOwnerGrantSpec,
    *,
    approved_at: datetime,
) -> Literal["created", "verified"]:
    if await _verify_existing(store, spec):
        return "verified"

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
        if await _verify_existing(store, spec):
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
    # Verify every existing head before creating any missing head. This prevents
    # a mismatch or revocation from being partially papered over by setup.
    existing = [await _verify_existing(store, spec) for spec in LOCAL_OWNER_GRANTS]
    statuses: list[LocalOwnerGrantStatus] = []
    for spec, is_existing in zip(LOCAL_OWNER_GRANTS, existing, strict=True):
        status: Literal["created", "verified"]
        status = "verified" if is_existing else await _create_or_verify(store, spec, approved_at=now)
        statuses.append(LocalOwnerGrantStatus(grant_ref=spec.grant_ref, status=status))
    return LocalOwnerAuthorityBootstrapResult(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        grants=tuple(statuses),
    )


__all__ = [
    "LOCAL_OWNER_ACTOR_REF",
    "LOCAL_OWNER_GRANTS",
    "LOCAL_OWNER_POLICY_REF",
    "LOCAL_OWNER_PRODUCT_ID",
    "LocalOwnerAuthorityBootstrapResult",
    "LocalOwnerAuthorityConflict",
    "LocalOwnerAuthorityDenied",
    "LocalOwnerAuthorityError",
    "LocalOwnerGrantStatus",
    "bootstrap_local_owner_authority",
]
