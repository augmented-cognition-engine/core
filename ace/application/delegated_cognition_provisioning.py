"""Human-admin provisioning for the bounded delegated-cognition service.

This is an operations-plane companion to delegated activation.  It authors one
registered SERVICE principal and exactly two product/scope-bound grants through
the existing agent-governance and governed-state ports.  It cannot mint tokens,
renew, widen, transfer, or grant any authority outside cognition review and
activation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from pydantic import ConfigDict, field_validator, model_validator
from pydantic_core import to_json

from ace.application.agent_governance import (
    ADMINISTER_LIFECYCLE_AUTHORITY,
    AGENT_GOVERNANCE_RECORD_SPACE,
    AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
    AgentGovernanceError,
    AgentGovernanceService,
)
from ace.core.agent_composition import AgentPrincipalV1Alpha1, AuthorityClass, PrincipalKind, PrincipalLifecycle
from ace.core.agent_governance import AgentGovernanceCoordinateV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.delegated_cognition import (
    ACTIVATION_AUTHORITY_CLASS,
    ACTIVATION_OPERATION,
    GRANT_PAYLOAD_CONTRACT,
    REVIEW_AUTHORITY_CLASS,
    REVIEW_OPERATION,
    CompositionAuthorityGrantMaterial,
)
from ace.core.records import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.runtime_use import AUTHORITY_GRANT_STATE_KIND
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateRevisionV1,
    ResolvedAuthorityGrantV1,
)
from ace.intelligence.contracts.agent_governance import (
    AgentPrincipalLifecycleRevisionV1Alpha1,
    PrincipalLifecycleState,
    exact_registration_reference,
)

DELEGATED_COGNITION_PROVISIONING_REQUEST_VERSION = "ace.cognition.delegated-service-provisioning-request/v1alpha1"
DELEGATED_COGNITION_PROVISIONING_RECEIPT_VERSION = "ace.cognition.delegated-service-provisioning-receipt/v1alpha1"
DELEGATED_COGNITION_PROVISIONING_RECORD_KIND = "delegated_cognition_provisioning_receipt"
DELEGATED_COGNITION_SERVICE_PROTOCOL = "ace.protocol.cognition-activation/v1alpha1"

_HUMAN_PREFIXES = ("user:", "human:", "local-owner:")
_FORBIDDEN_AUTHORITY_CLASSES = frozenset(
    {
        AuthorityClass.INTELLIGENCE_BUILD,
        AuthorityClass.OBSERVE_READ,
        AuthorityClass.DERIVE_PROPOSE,
        AuthorityClass.EXECUTE_EXTERNAL,
        AuthorityClass.DELIVER_EXPORT,
        AuthorityClass.ADMINISTER_LIFECYCLE,
    }
)


class DelegatedCognitionProvisioningError(RuntimeError):
    """Provisioning failed closed without creating a reusable authority path."""


class _Strict(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _derive(instance: _Strict, *, id_field: str, digest_field: str, prefix: str) -> None:
    digest = canonical_hash(instance.model_dump(mode="json", exclude={id_field, digest_field}))
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in {None, expected_id}:
        raise ValueError(f"{id_field} does not match exact provisioning material")
    if getattr(instance, digest_field) not in {None, expected_digest}:
        raise ValueError(f"{digest_field} does not match exact provisioning material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class DelegatedCognitionProvisioningRequestV1Alpha1(_Strict):
    """One non-renewable, non-transferable human-admin provisioning instruction."""

    contract: Literal["ace.cognition.delegated-service-provisioning-request/v1alpha1"] = (
        DELEGATED_COGNITION_PROVISIONING_REQUEST_VERSION
    )
    product_id: str
    principal: AgentPrincipalV1Alpha1
    service_actor_ref: str
    scope_ref: str
    policy_ref: str
    review_grant_ref: str
    activation_grant_ref: str
    admin_actor_ref: str
    admin_actor_class: Literal["human"] = "human"
    admin_grant_ref: str
    suspended_approval_receipt_ref: str
    active_approval_receipt_ref: str
    review_grant_approval_receipt_ref: str
    activation_grant_approval_receipt_ref: str
    provisioned_at: datetime
    request_id: str | None = None
    request_digest: str | None = None

    @field_validator("provisioned_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, "provisioned_at")

    @model_validator(mode="after")
    def validate_exact_boundary(self) -> Self:
        if not self.product_id.startswith("product:") or self.principal.product_id != self.product_id:
            raise ValueError("provisioning requires one exact product scope")
        if self.principal.principal_kind is not PrincipalKind.SERVICE:
            raise ValueError("provisioning accepts only a SERVICE principal")
        if self.principal.lifecycle is not PrincipalLifecycle.ACTIVE:
            raise ValueError("the registration snapshot must describe the intended active SERVICE")
        if DELEGATED_COGNITION_SERVICE_PROTOCOL not in self.principal.supported_protocol_versions:
            raise ValueError("SERVICE principal lacks the delegated cognition protocol")
        if not self.admin_actor_ref.startswith(_HUMAN_PREFIXES):
            raise ValueError("provisioning requires an explicit human administrator")
        if self.admin_actor_ref in {self.service_actor_ref, str(self.principal.principal_id)}:
            raise ValueError("a SERVICE cannot provision or administer itself")
        if self.service_actor_ref == str(self.principal.principal_id) or not self.service_actor_ref.startswith(
            "service:"
        ):
            raise ValueError("service token actor and registered principal must be distinct exact identities")
        if self.principal.owner_ref != self.admin_actor_ref:
            raise ValueError("registration owner must be the provisioning administrator")
        if self.review_grant_ref == self.activation_grant_ref:
            raise ValueError("review and activation require distinct grants")
        if (
            len(
                {
                    self.suspended_approval_receipt_ref,
                    self.active_approval_receipt_ref,
                    self.review_grant_approval_receipt_ref,
                    self.activation_grant_approval_receipt_ref,
                }
            )
            != 4
        ):
            raise ValueError("each provisioning decision requires a distinct approval receipt")
        _derive(self, id_field="request_id", digest_field="request_digest", prefix="delegated_service_provisioning")
        return self


class DelegatedCognitionProvisioningReceiptV1Alpha1(_Strict):
    """Durable proof of the exact principal and two grants that were provisioned."""

    contract: Literal["ace.cognition.delegated-service-provisioning-receipt/v1alpha1"] = (
        DELEGATED_COGNITION_PROVISIONING_RECEIPT_VERSION
    )
    governance: AgentGovernanceCoordinateV1Alpha1
    request_ref: str
    request_digest: str
    principal_ref: str
    principal_digest: str
    service_actor_ref: str
    admin_actor_ref: str
    admin_grant_ref: str
    review_grant_ref: str
    review_grant_hash: str
    review_grant_commit_receipt_ref: str
    activation_grant_ref: str
    activation_grant_hash: str
    activation_grant_commit_receipt_ref: str
    suspended_lifecycle_revision_ref: str
    active_lifecycle_revision_ref: str
    scope_ref: str
    policy_ref: str
    authority_classes: tuple[AuthorityClass, AuthorityClass]
    operations: tuple[str, str]
    reusable_authority: Literal[False] = False
    renewable: Literal[False] = False
    transferable: Literal[False] = False
    external_effect_authority: Literal[False] = False
    provisioned_at: datetime
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("provisioned_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, "provisioned_at")

    @model_validator(mode="after")
    def validate_exact_authority(self) -> Self:
        expected_classes = tuple(sorted((REVIEW_AUTHORITY_CLASS, ACTIVATION_AUTHORITY_CLASS), key=lambda x: x.value))
        if self.authority_classes != expected_classes:
            raise ValueError("receipt authority set must be exact")
        if self.operations != tuple(sorted((REVIEW_OPERATION, ACTIVATION_OPERATION))):
            raise ValueError("receipt operation set must be exact")
        if set(self.authority_classes).intersection(_FORBIDDEN_AUTHORITY_CLASSES):
            raise ValueError("receipt contains forbidden authority")
        _derive(
            self, id_field="receipt_id", digest_field="receipt_digest", prefix="delegated_service_provisioning_receipt"
        )
        return self


def delegated_cognition_service_token_claims(
    receipt: DelegatedCognitionProvisioningReceiptV1Alpha1,
) -> dict[str, object]:
    """Return the only supported signed-token claims for this SERVICE.

    The trusted operator signs these with the existing host token issuer.  The
    service never receives local-owner or lifecycle authority in its JWT.
    """

    return {
        "sub": receipt.service_actor_ref,
        "product": receipt.governance.product_id,
        "authorities": [],
        "local_owner": False,
        "principal_kind": PrincipalKind.SERVICE.value,
        "agent_principal": receipt.principal_ref,
    }


def _grant(
    request: DelegatedCognitionProvisioningRequestV1Alpha1,
    *,
    grant_ref: str,
    authority_class: AuthorityClass,
    operation: str,
    effective_at: datetime,
) -> CompositionAuthorityGrantMaterial:
    fields = {
        "contract": GRANT_PAYLOAD_CONTRACT,
        "grant_ref": grant_ref,
        "product_id": request.product_id,
        "actor_ref": request.service_actor_ref,
        "participant_principal_ref": str(request.principal.principal_id),
        "delegator_ref": request.admin_actor_ref,
        "authority_class": authority_class,
        "operations": (operation,),
        "scope_ref": request.scope_ref,
        "policy_ref": request.policy_ref,
        "lifecycle": "active",
        "effective_at": effective_at,
        "expires_at": None,
        "revoked_at": None,
        "delegation_ceiling": tuple(
            sorted((REVIEW_AUTHORITY_CLASS, ACTIVATION_AUTHORITY_CLASS), key=lambda item: item.value)
        ),
    }
    provisional = CompositionAuthorityGrantMaterial(**fields, grant_hash="0" * 64)
    return CompositionAuthorityGrantMaterial(
        **fields,
        grant_hash=canonical_hash(provisional.model_dump(mode="json", exclude={"grant_hash"})),
    )


class DelegatedCognitionProvisioningService:
    """Provision one exact delegated-cognition SERVICE under human authority."""

    def __init__(self, *, governance: AgentGovernanceService) -> None:
        self.governance = governance

    async def _commit_grant(
        self,
        request: DelegatedCognitionProvisioningRequestV1Alpha1,
        *,
        grant: CompositionAuthorityGrantMaterial,
        approval_receipt_ref: str,
    ):
        head = await self.governance.governed_store.load_head(
            state_kind=AUTHORITY_GRANT_STATE_KIND,
            product_id=request.product_id,
            state_id=grant.grant_ref,
        )
        material_hash = canonical_hash(grant.model_dump(mode="json"))
        revision_id = f"authority_grant_revision:{material_hash[:32]}"
        if head is not None:
            revision = await self.governance.governed_store.load_revision(
                head.revision_id, product_id=request.product_id
            )
            receipt = await self.governance.governed_store.load_receipt(
                head.commit_receipt_id, product_id=request.product_id
            )
            if (
                head.sequence == 1
                and head.revision_id == revision_id
                and revision is not None
                and receipt is not None
                and revision.material_hash == material_hash
                and CompositionAuthorityGrantMaterial.model_validate(revision.payload, strict=False) == grant
                and any(
                    item.grant_ref == grant.grant_ref and item.grant_hash == grant.grant_hash
                    for item in receipt.authority_grants
                )
            ):
                return receipt
            raise DelegatedCognitionProvisioningError(
                "grant already exists; renewal, widening, and transfer are forbidden"
            )

        subject_ref = f"approval_subject:delegated-cognition-provision:{grant.grant_ref}"
        try:
            approval = await self.governance.authority.resolve_approval(
                receipt_ref=approval_receipt_ref,
                product_id=request.product_id,
                subject_ref=subject_ref,
                actor_ref=request.admin_actor_ref,
                effective_at=grant.effective_at,
            )
            admin = await self.governance.authority.resolve_grant(
                grant_ref=request.admin_grant_ref,
                product_id=request.product_id,
                authority=ADMINISTER_LIFECYCLE_AUTHORITY,
                effective_at=grant.effective_at,
            )
        except Exception:
            raise DelegatedCognitionProvisioningError("current human administrative authority is unavailable") from None
        if (
            approval.product_id != request.product_id
            or approval.subject_ref != subject_ref
            or approval.actor_ref != request.admin_actor_ref
            or admin.grant_ref != request.admin_grant_ref
            or admin.product_id != request.product_id
            or admin.authority != ADMINISTER_LIFECYCLE_AUTHORITY
            or admin.effective_at != grant.effective_at
            or (admin.expires_at is not None and admin.expires_at <= grant.effective_at)
        ):
            raise DelegatedCognitionProvisioningError("human administrative evidence is not exact")
        resolved_grant = ResolvedAuthorityGrantV1(
            grant_ref=grant.grant_ref,
            product_id=grant.product_id,
            authority=grant.authority_class.value,
            grant_hash=grant.grant_hash,
            effective_at=grant.effective_at,
            expires_at=None,
        )
        revision = GovernedStateRevisionV1(
            state_kind=AUTHORITY_GRANT_STATE_KIND,
            product_id=request.product_id,
            state_id=grant.grant_ref,
            sequence=1,
            revision_id=revision_id,
            material_hash=material_hash,
            approval_subject_ref=subject_ref,
            payload_contract=GRANT_PAYLOAD_CONTRACT,
            payload=grant.model_dump(mode="python"),
        )
        commit = GovernedStateCommitRequestV1(
            revision=revision,
            actor_ref=request.admin_actor_ref,
            approval=approval,
            authority_grants=(admin, resolved_grant),
            committed_at=grant.effective_at,
        )
        expected = commit.receipt()
        try:
            return await self.governance.governed_store.commit(commit)
        except Exception:
            recovered = await self.governance.governed_store.load_receipt(
                str(expected.receipt_id), product_id=request.product_id
            )
            if recovered == expected:
                return recovered
            raise DelegatedCognitionProvisioningError("grant provisioning commit failed closed") from None

    async def provision(
        self,
        request: DelegatedCognitionProvisioningRequestV1Alpha1,
    ) -> DelegatedCognitionProvisioningReceiptV1Alpha1:
        request = DelegatedCognitionProvisioningRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        coordinate = AgentGovernanceCoordinateV1Alpha1(
            product_id=request.product_id,
            principal_key=request.principal.principal_key,
        )
        registration = exact_registration_reference(request.principal)
        current = await self.governance.governed_store.load_head(
            state_kind=AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
            product_id=request.product_id,
            state_id=str(coordinate.governance_id),
        )
        suspended = AgentPrincipalLifecycleRevisionV1Alpha1(
            governance=coordinate,
            registration_snapshot=registration,
            registration_implementation_ref=request.principal.implementation_ref,
            registration_protocol_refs=request.principal.supported_protocol_versions,
            state=PrincipalLifecycleState.SUSPENDED,
            sequence=1,
            approval_receipt_ref=request.suspended_approval_receipt_ref,
            actor_ref=request.admin_actor_ref,
            occurred_at=request.provisioned_at,
        )
        active = AgentPrincipalLifecycleRevisionV1Alpha1(
            governance=coordinate,
            registration_snapshot=registration,
            registration_implementation_ref=request.principal.implementation_ref,
            registration_protocol_refs=request.principal.supported_protocol_versions,
            state=PrincipalLifecycleState.ACTIVE,
            sequence=2,
            prior_revision_id=str(suspended.lifecycle_revision_id),
            approval_receipt_ref=request.active_approval_receipt_ref,
            actor_ref=request.admin_actor_ref,
            occurred_at=request.provisioned_at + timedelta(microseconds=1),
        )
        if current is None:
            try:
                await self.governance.admit_principal_lifecycle(
                    suspended,
                    registration=request.principal,
                    admin_grant_ref=request.admin_grant_ref,
                    committed_at=suspended.occurred_at,
                )
                await self.governance.admit_principal_lifecycle(
                    active,
                    registration=request.principal,
                    admin_grant_ref=request.admin_grant_ref,
                    committed_at=active.occurred_at,
                )
            except AgentGovernanceError as exc:
                raise DelegatedCognitionProvisioningError(str(exc)) from exc
        else:
            revision = await self.governance.governed_store.load_revision(
                current.revision_id, product_id=request.product_id
            )
            if revision is None or revision.revision_id != active.lifecycle_revision_id:
                raise DelegatedCognitionProvisioningError(
                    "principal already exists; renewal, replacement, and transfer are forbidden"
                )

        review = _grant(
            request,
            grant_ref=request.review_grant_ref,
            authority_class=REVIEW_AUTHORITY_CLASS,
            operation=REVIEW_OPERATION,
            effective_at=request.provisioned_at + timedelta(microseconds=2),
        )
        activation = _grant(
            request,
            grant_ref=request.activation_grant_ref,
            authority_class=ACTIVATION_AUTHORITY_CLASS,
            operation=ACTIVATION_OPERATION,
            effective_at=request.provisioned_at + timedelta(microseconds=2),
        )
        review_commit = await self._commit_grant(
            request, grant=review, approval_receipt_ref=request.review_grant_approval_receipt_ref
        )
        activation_commit = await self._commit_grant(
            request, grant=activation, approval_receipt_ref=request.activation_grant_approval_receipt_ref
        )
        receipt = DelegatedCognitionProvisioningReceiptV1Alpha1(
            governance=coordinate,
            request_ref=str(request.request_id),
            request_digest=str(request.request_digest),
            principal_ref=str(request.principal.principal_id),
            principal_digest=str(request.principal.principal_digest),
            service_actor_ref=request.service_actor_ref,
            admin_actor_ref=request.admin_actor_ref,
            admin_grant_ref=request.admin_grant_ref,
            review_grant_ref=review.grant_ref,
            review_grant_hash=review.grant_hash,
            review_grant_commit_receipt_ref=str(review_commit.receipt_id),
            activation_grant_ref=activation.grant_ref,
            activation_grant_hash=activation.grant_hash,
            activation_grant_commit_receipt_ref=str(activation_commit.receipt_id),
            suspended_lifecycle_revision_ref=str(suspended.lifecycle_revision_id),
            active_lifecycle_revision_ref=str(active.lifecycle_revision_id),
            scope_ref=request.scope_ref,
            policy_ref=request.policy_ref,
            authority_classes=tuple(
                sorted((REVIEW_AUTHORITY_CLASS, ACTIVATION_AUTHORITY_CLASS), key=lambda item: item.value)
            ),
            operations=tuple(sorted((REVIEW_OPERATION, ACTIVATION_OPERATION))),
            provisioned_at=request.provisioned_at + timedelta(microseconds=2),
        )
        record = ImmutableRecordV1(
            product_id=request.product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            record_kind=DELEGATED_COGNITION_PROVISIONING_RECORD_KIND,
            record_key=str(receipt.receipt_id),
            payload_contract=receipt.contract,
            payload=receipt.model_dump(mode="python"),
            as_of=receipt.provisioned_at,
            available_at=receipt.provisioned_at,
            processing_order=0,
        )
        await self.governance.audit_store.append(
            AppendOnlyTransactionRequestV1(
                product_id=request.product_id,
                record_space=AGENT_GOVERNANCE_RECORD_SPACE,
                transaction_key=str(receipt.receipt_id),
                records=(record,),
                submitted_at=receipt.provisioned_at,
            )
        )
        return receipt

    async def load_receipt(
        self,
        *,
        product_id: str,
        receipt_id: str,
    ) -> DelegatedCognitionProvisioningReceiptV1Alpha1 | None:
        storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            record_kind=DELEGATED_COGNITION_PROVISIONING_RECORD_KIND,
            record_key=receipt_id,
        )
        record = await self.governance.audit_store.load_record(
            storage_id,
            product_id=product_id,
            record_space=AGENT_GOVERNANCE_RECORD_SPACE,
            record_kind=DELEGATED_COGNITION_PROVISIONING_RECORD_KIND,
        )
        if record is None:
            return None
        try:
            receipt = DelegatedCognitionProvisioningReceiptV1Alpha1.model_validate_json(
                to_json(record.payload),
                strict=True,
            )
        except ValueError:
            raise DelegatedCognitionProvisioningError("durable provisioning receipt is malformed") from None
        if receipt.contract != record.payload_contract or canonical_hash(
            receipt.model_dump(mode="json")
        ) != canonical_hash(json.loads(to_json(record.payload))):
            raise DelegatedCognitionProvisioningError("durable provisioning receipt is not exact")
        return receipt


__all__ = [
    "DELEGATED_COGNITION_PROVISIONING_RECEIPT_VERSION",
    "DELEGATED_COGNITION_PROVISIONING_RECORD_KIND",
    "DELEGATED_COGNITION_PROVISIONING_REQUEST_VERSION",
    "DELEGATED_COGNITION_SERVICE_PROTOCOL",
    "DelegatedCognitionProvisioningError",
    "DelegatedCognitionProvisioningReceiptV1Alpha1",
    "DelegatedCognitionProvisioningRequestV1Alpha1",
    "DelegatedCognitionProvisioningService",
    "delegated_cognition_service_token_claims",
]
