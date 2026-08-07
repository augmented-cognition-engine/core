"""Application bridge for Core-committed Domain Activation revisions.

Intelligence owns the activation payload and its exact Pack binding.  Core owns
approval and grant resolution, product scope, durable state, optimistic head
admission, transactionality, and audit receipts.  This bridge composes those
responsibilities without making either bounded context import the other.

A prepared revision expresses desired state.  A committed revision has passed
Core admission and is durable.  Neither state grants live execution authority;
live consumers must separately resolve the current committed head and current
runtime authority at their point of use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ace.core.contracts import canonical_hash
from ace.core.state import (
    CoreAuthorityResolver,
    GovernedStateCommitReceiptV1,
    GovernedStateCommitRequestV1,
    GovernedStateRevisionV1,
    GovernedStateStore,
)
from ace.intelligence.contracts.activation import (
    DOMAIN_ACTIVATION_REVISION_VERSION,
    DomainActivationRevisionV1,
)
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from ace.intelligence.packs.runtime import (
    PreparedActivationBinding,
    bind_prepared_activation,
)

DOMAIN_ACTIVATION_STATE_KIND = "domain_activation"


class DomainActivationAdmissionError(RuntimeError):
    """Prepared or persisted activation material failed closed at admission."""


@dataclass(frozen=True, slots=True)
class CommittedDomainActivation:
    """Exact durable activation revision plus its Core commit receipt."""

    revision: DomainActivationRevisionV1
    commit_receipt: GovernedStateCommitReceiptV1
    authority_stage: Literal["committed"] = "committed"

    @property
    def live_authority(self) -> Literal[False]:
        """Committed state is intentionally insufficient for live execution."""

        return False


@dataclass(frozen=True, slots=True)
class CommittedActivationBinding:
    """Exact Pack binding backed by a Core commit, still not live authority."""

    prepared_binding: PreparedActivationBinding
    commit_receipt: GovernedStateCommitReceiptV1
    authority_stage: Literal["committed"] = "committed"

    @property
    def live_authority(self) -> Literal[False]:
        return False


def _revalidate_revision(revision: DomainActivationRevisionV1) -> DomainActivationRevisionV1:
    try:
        return DomainActivationRevisionV1.model_validate(revision.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DomainActivationAdmissionError("activation revision failed exact revalidation") from exc


def _activation_id(product_id: str, activation_key: str) -> str:
    return f"domain_activation:{canonical_hash([product_id, activation_key])[:32]}"


def _envelope(revision: DomainActivationRevisionV1) -> GovernedStateRevisionV1:
    if revision.activation_id is None or revision.revision_id is None or revision.revision_hash is None:
        raise DomainActivationAdmissionError("activation revision is missing its derived identity")
    return GovernedStateRevisionV1(
        state_kind=DOMAIN_ACTIVATION_STATE_KIND,
        product_id=revision.spec.product_id,
        state_id=revision.activation_id,
        sequence=revision.revision,
        revision_id=revision.revision_id,
        material_hash=revision.revision_hash,
        prior_revision_id=revision.prior_revision_id,
        approval_subject_ref=str(revision.spec.spec_id),
        payload_contract=DOMAIN_ACTIVATION_REVISION_VERSION,
        payload=revision.model_dump(mode="python"),
    )


def _validate_committed_pair(
    revision: DomainActivationRevisionV1,
    receipt: GovernedStateCommitReceiptV1,
) -> CommittedDomainActivation:
    envelope = _envelope(revision)
    expected = {
        "state_kind": envelope.state_kind,
        "product_id": envelope.product_id,
        "state_id": envelope.state_id,
        "sequence": envelope.sequence,
        "revision_id": envelope.revision_id,
        "material_hash": envelope.material_hash,
        "prior_revision_id": envelope.prior_revision_id,
    }
    actual = {name: getattr(receipt, name) for name in expected}
    if actual != expected:
        raise DomainActivationAdmissionError("Core commit receipt does not bind the exact activation revision")
    return CommittedDomainActivation(revision=revision, commit_receipt=receipt)


class DomainActivationAdmissionService:
    """Resolve Core authority, atomically admit, and reload exact revisions."""

    def __init__(self, *, store: GovernedStateStore, authority: CoreAuthorityResolver) -> None:
        self.store = store
        self.authority = authority

    async def admit(
        self,
        revision: DomainActivationRevisionV1,
        *,
        expected_head_revision_id: str | None,
        committed_at: datetime,
    ) -> CommittedDomainActivation:
        validated = _revalidate_revision(revision)
        if committed_at.tzinfo is None or committed_at.utcoffset() is None:
            raise DomainActivationAdmissionError("commit time must include a timezone")
        if validated.occurred_at > committed_at:
            raise DomainActivationAdmissionError("commit cannot predate the prepared activation transition")
        if validated.prior_revision_id != expected_head_revision_id:
            raise DomainActivationAdmissionError(
                "expected head must exactly equal the prepared revision's prior revision"
            )
        if validated.spec.spec_id is None:
            raise DomainActivationAdmissionError("activation specification is missing its derived identity")

        approval = await self.authority.resolve_approval(
            receipt_ref=validated.approval_receipt_ref,
            product_id=validated.spec.product_id,
            subject_ref=validated.spec.spec_id,
            actor_ref=validated.actor_ref,
            effective_at=validated.occurred_at,
        )
        if (
            approval.receipt_ref != validated.approval_receipt_ref
            or approval.product_id != validated.spec.product_id
            or approval.subject_ref != validated.spec.spec_id
            or approval.actor_ref != validated.actor_ref
            or approval.approved_at > validated.occurred_at
        ):
            raise DomainActivationAdmissionError(
                "approval receipt did not resolve to the exact activation specification, actor, time, and product"
            )

        grants = []
        for binding in validated.spec.authority_bindings:
            grant = await self.authority.resolve_grant(
                grant_ref=binding.grant_ref,
                product_id=validated.spec.product_id,
                authority=binding.authority,
                effective_at=validated.occurred_at,
            )
            if (
                grant.grant_ref != binding.grant_ref
                or grant.product_id != validated.spec.product_id
                or grant.authority != binding.authority
                or grant.effective_at != validated.occurred_at
                or (grant.expires_at is not None and grant.expires_at <= validated.occurred_at)
            ):
                raise DomainActivationAdmissionError(
                    f"authority grant {binding.request_id} did not resolve for the exact product and transition time"
                )
            grants.append(grant)

        request = GovernedStateCommitRequestV1(
            revision=_envelope(validated),
            expected_head_revision_id=expected_head_revision_id,
            actor_ref=validated.actor_ref,
            approval=approval,
            authority_grants=tuple(grants),
            committed_at=committed_at,
        )
        receipt = await self.store.commit(request)
        return _validate_committed_pair(validated, receipt)

    async def reload(
        self,
        *,
        product_id: str,
        activation_key: str,
    ) -> CommittedDomainActivation | None:
        activation_id = _activation_id(product_id, activation_key)
        head = await self.store.load_head(
            state_kind=DOMAIN_ACTIVATION_STATE_KIND,
            product_id=product_id,
            state_id=activation_id,
        )
        if head is None:
            return None
        if (
            head.state_kind != DOMAIN_ACTIVATION_STATE_KIND
            or head.product_id != product_id
            or head.state_id != activation_id
        ):
            raise DomainActivationAdmissionError("persisted activation head crossed its exact product scope")
        envelope = await self.store.load_revision(head.revision_id, product_id=product_id)
        receipt = await self.store.load_receipt(head.commit_receipt_id, product_id=product_id)
        if envelope is None or receipt is None:
            raise DomainActivationAdmissionError("persisted activation head has an incomplete commit chain")
        if envelope.payload_contract != DOMAIN_ACTIVATION_REVISION_VERSION:
            raise DomainActivationAdmissionError("persisted activation revision uses an unsupported contract")
        try:
            revision = DomainActivationRevisionV1.model_validate(envelope.payload)
        except (TypeError, ValueError) as exc:
            raise DomainActivationAdmissionError("persisted activation revision failed exact revalidation") from exc
        expected_envelope = _envelope(revision)
        envelope_fields = (
            "contract",
            "state_kind",
            "product_id",
            "state_id",
            "sequence",
            "revision_id",
            "material_hash",
            "prior_revision_id",
            "approval_subject_ref",
            "payload_contract",
        )
        if any(getattr(expected_envelope, name) != getattr(envelope, name) for name in envelope_fields):
            raise DomainActivationAdmissionError("persisted envelope does not match exact activation material")
        if (
            head.sequence != revision.revision
            or head.revision_id != revision.revision_id
            or head.commit_receipt_id != receipt.receipt_id
        ):
            raise DomainActivationAdmissionError("persisted head does not match its exact commit chain")
        return _validate_committed_pair(revision, receipt)

    async def load_exact(
        self,
        *,
        product_id: str,
        revision_id: str,
        commit_receipt_id: str,
    ) -> CommittedDomainActivation | None:
        """Load one exact historical committed revision without requiring it is current."""

        try:
            envelope = await self.store.load_revision(revision_id, product_id=product_id)
            receipt = await self.store.load_receipt(
                commit_receipt_id,
                product_id=product_id,
            )
        except Exception:
            raise DomainActivationAdmissionError("historical activation commit failed exact load") from None
        if envelope is None and receipt is None:
            return None
        if envelope is None or receipt is None:
            raise DomainActivationAdmissionError("historical activation commit chain is incomplete")
        if (
            envelope.product_id != product_id
            or envelope.revision_id != revision_id
            or receipt.product_id != product_id
            or receipt.revision_id != revision_id
            or receipt.receipt_id != commit_receipt_id
            or envelope.payload_contract != DOMAIN_ACTIVATION_REVISION_VERSION
        ):
            raise DomainActivationAdmissionError("historical activation coordinates crossed exact commit material")
        try:
            revision = DomainActivationRevisionV1.model_validate(envelope.payload)
            expected_envelope = _envelope(revision)
        except Exception:
            raise DomainActivationAdmissionError("historical activation revision failed exact revalidation") from None
        envelope_fields = (
            "contract",
            "state_kind",
            "product_id",
            "state_id",
            "sequence",
            "revision_id",
            "material_hash",
            "prior_revision_id",
            "approval_subject_ref",
            "payload_contract",
        )
        if any(getattr(expected_envelope, name) != getattr(envelope, name) for name in envelope_fields):
            raise DomainActivationAdmissionError("historical activation envelope changed from exact revision material")
        return _validate_committed_pair(revision, receipt)


def bind_committed_activation(
    *,
    pack: CompiledDomainPackV1,
    committed: CommittedDomainActivation,
) -> CommittedActivationBinding:
    """Bind exact Pack IR to a committed revision without claiming live authority."""

    validated = _validate_committed_pair(committed.revision, committed.commit_receipt)
    prepared = bind_prepared_activation(pack=pack, revision=validated.revision)
    return CommittedActivationBinding(
        prepared_binding=prepared,
        commit_receipt=validated.commit_receipt,
    )


__all__ = [
    "CommittedActivationBinding",
    "CommittedDomainActivation",
    "DOMAIN_ACTIVATION_STATE_KIND",
    "DomainActivationAdmissionError",
    "DomainActivationAdmissionService",
    "bind_committed_activation",
]
