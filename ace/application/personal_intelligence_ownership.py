"""Product-scoped export and two-phase delete for personal Intelligence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ace.core.contracts import canonical_hash
from ace.core.personal_intelligence_ownership import (
    WORKSPACE_DERIVED_ARTIFACT_KINDS,
    DerivedArtifactCoverageV1Alpha1,
    DerivedArtifactErasureEntryV1Alpha1,
    PersonalIntelligenceDeleteConfirmationV1Alpha1,
    PersonalIntelligenceDeletePreviewRequestV1Alpha1,
    PersonalIntelligenceDeletePreviewV1Alpha1,
    PersonalIntelligenceDeletionProofV1Alpha1,
    PersonalIntelligenceExportArtifactV1Alpha1,
    PersonalIntelligenceExportRequestV1Alpha1,
    derive_erasure_entries,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReferenceV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1

PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE = "personal_intelligence_ownership"
PERSONAL_INTELLIGENCE_DELETION_PROOF_RECORD_KIND = "personal_intelligence_deletion_proof"


class PersonalIntelligenceOwnershipError(RuntimeError):
    """A personal ownership operation failed closed."""


class PersonalIntelligenceDeletePreviewStale(PersonalIntelligenceOwnershipError):
    """The primary record set changed after the caller reviewed the preview."""


class PersonalIntelligenceOwnershipStore(ImmutableRecordStore, Protocol):
    """Immutable store with Core's exact atomic erasure primitive."""

    async def erase_records_atomically(
        self,
        *,
        product_id: str,
        expected_records: tuple[ImmutableRecordReferenceV1, ...],
        receipt_request: AppendOnlyTransactionRequestV1,
    ) -> AppendOnlyTransactionReceiptV1: ...


class PersonalIntelligenceDerivativeErasurePort(Protocol):
    """Host-owned enumeration and erasure of workspace derivative artifacts.

    enumerate_derivatives returns exactly one coverage entry per workspace
    derived-artifact kind (embeddings, vector material, graph projections,
    graph edges, caches, summaries) with the exact live count and a
    covered/surviving disposition. erase_derivatives must make the preview's
    coverage true — remove every covered artifact and re-probe absence — and
    return the attested erasure entries, or raise.
    """

    async def enumerate_derivatives(self, *, product_id: str) -> tuple[DerivedArtifactCoverageV1Alpha1, ...]: ...

    async def erase_derivatives(
        self,
        *,
        product_id: str,
        coverage: tuple[DerivedArtifactCoverageV1Alpha1, ...],
    ) -> tuple[DerivedArtifactErasureEntryV1Alpha1, ...]: ...


class PersonalIntelligenceOwnershipAuthorizationPort(Protocol):
    """Host-owned authorization check; successful return grants no reusable authority."""

    async def authorize(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        operation: str,
        subject_ref: str,
        evaluated_at: datetime,
    ) -> None: ...


@dataclass(frozen=True)
class PersonalIntelligenceDeletionResult:
    proof: PersonalIntelligenceDeletionProofV1Alpha1
    transaction_receipt_ref: str


def _owned_records(records: tuple[ImmutableRecordV1, ...]) -> tuple[ImmutableRecordV1, ...]:
    """Exclude ownership proof/control evidence from content export and deletion."""

    selected = tuple(item for item in records if item.record_space != PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE)
    return tuple(sorted(selected, key=lambda item: str(item.storage_id)))


def _references(records: tuple[ImmutableRecordV1, ...]) -> tuple[ImmutableRecordReferenceV1, ...]:
    return tuple(item.reference() for item in records)


def _record_set_digest(records: tuple[ImmutableRecordReferenceV1, ...]) -> str:
    material = tuple((item.storage_id, item.material_hash) for item in records)
    return f"sha256:{canonical_hash(material)}"


class PersonalIntelligenceOwnershipService:
    """Give one authenticated actor portable records and a guarded delete path.

    This service is intentionally local-store scoped.  It does not enumerate or
    erase native database backups, user-created exports, caches, connector-owned
    bodies, or third-party copies.  Hosts must quiesce writes from paths that do
    not share this service instance while a confirmed deletion is in progress.
    """

    def __init__(
        self,
        *,
        store: PersonalIntelligenceOwnershipStore,
        authorization: PersonalIntelligenceOwnershipAuthorizationPort,
        derivatives: PersonalIntelligenceDerivativeErasurePort | None = None,
    ) -> None:
        self.store = store
        self.authorization = authorization
        self.derivatives = derivatives
        self._deletion_lock = asyncio.Lock()

    async def _derivative_coverage(self, *, product_id: str) -> tuple[DerivedArtifactCoverageV1Alpha1, ...]:
        """Enumerate live derivative coverage, requiring every workspace kind exactly once."""

        if self.derivatives is None:
            return ()
        try:
            coverage = await self.derivatives.enumerate_derivatives(product_id=product_id)
        except Exception as exc:
            raise PersonalIntelligenceOwnershipError(
                "derivative-artifact enumeration failed; deletion cannot state exact counts"
            ) from exc
        kinds = tuple(entry.artifact_kind for entry in coverage)
        if sorted(kinds) != sorted(WORKSPACE_DERIVED_ARTIFACT_KINDS):
            raise PersonalIntelligenceOwnershipError(
                "derivative-artifact enumeration must name every workspace kind exactly once"
            )
        return coverage

    async def export(
        self,
        request: PersonalIntelligenceExportRequestV1Alpha1,
    ) -> PersonalIntelligenceExportArtifactV1Alpha1:
        try:
            request = PersonalIntelligenceExportRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
            await self.authorization.authorize(
                authenticated_context=request.authenticated_context,
                operation="export_personal_intelligence",
                subject_ref=str(request.request_id),
                evaluated_at=request.requested_at,
            )
            product_records = await self.store.scan_product_records(product_id=request.authenticated_context.product_id)
        except Exception as exc:
            raise PersonalIntelligenceOwnershipError(
                "personal Intelligence export failed exact validation or product scan"
            ) from exc
        records = _owned_records(product_records)
        references = _references(records)
        return PersonalIntelligenceExportArtifactV1Alpha1(
            request_ref=str(request.request_id),
            product_id=request.authenticated_context.product_id,
            requested_by_ref=request.authenticated_context.actor_ref,
            records=records,
            record_count=len(records),
            record_set_digest=_record_set_digest(references),
            created_at=request.requested_at,
        )

    async def preview_delete(
        self,
        request: PersonalIntelligenceDeletePreviewRequestV1Alpha1,
    ) -> PersonalIntelligenceDeletePreviewV1Alpha1:
        try:
            request = PersonalIntelligenceDeletePreviewRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
            await self.authorization.authorize(
                authenticated_context=request.authenticated_context,
                operation="preview_personal_intelligence_deletion",
                subject_ref=str(request.request_id),
                evaluated_at=request.requested_at,
            )
            product_records = await self.store.scan_product_records(product_id=request.authenticated_context.product_id)
        except Exception as exc:
            raise PersonalIntelligenceOwnershipError(
                "personal Intelligence delete preview failed exact validation or product scan"
            ) from exc
        records = _owned_records(product_records)
        if not records:
            raise PersonalIntelligenceOwnershipError(
                "personal Intelligence delete preview found no removable immutable records"
            )
        coverage = await self._derivative_coverage(product_id=request.authenticated_context.product_id)
        references = _references(records)
        return PersonalIntelligenceDeletePreviewV1Alpha1(
            request_ref=str(request.request_id),
            product_id=request.authenticated_context.product_id,
            requested_by_ref=request.authenticated_context.actor_ref,
            records=references,
            record_count=len(references),
            record_set_digest=_record_set_digest(references),
            created_at=request.requested_at,
            expires_at=request.expires_at,
            derived_artifacts=coverage,
        )

    async def confirm_delete(
        self,
        confirmation: PersonalIntelligenceDeleteConfirmationV1Alpha1,
    ) -> PersonalIntelligenceDeletionResult:
        try:
            confirmation = PersonalIntelligenceDeleteConfirmationV1Alpha1.model_validate(
                confirmation.model_dump(mode="python")
            )
            await self.authorization.authorize(
                authenticated_context=confirmation.authenticated_context,
                operation="confirm_personal_intelligence_deletion",
                subject_ref=str(confirmation.confirmation_id),
                evaluated_at=confirmation.confirmed_at,
            )
        except Exception as exc:
            raise PersonalIntelligenceOwnershipError(
                "personal Intelligence deletion confirmation failed exact validation"
            ) from exc
        proof = self._proof(confirmation)
        proof_record = self._proof_record(proof)
        async with self._deletion_lock:
            replay = await self._prior_result(
                confirmation=confirmation,
                proof=proof,
                proof_record=proof_record,
            )
            if replay is not None:
                return replay
            current = _owned_records(await self.store.scan_product_records(product_id=confirmation.preview.product_id))
            current_references = _references(current)
            if current_references != confirmation.preview.records:
                raise PersonalIntelligenceDeletePreviewStale(
                    "immutable records changed after preview; request and review a new delete preview"
                )
            await self._erase_derivatives(confirmation)
            transaction_request = AppendOnlyTransactionRequestV1(
                product_id=confirmation.preview.product_id,
                record_space=PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE,
                transaction_key=str(confirmation.confirmation_id),
                records=(proof_record,),
                submitted_at=confirmation.confirmed_at,
            )
            try:
                transaction = await self.store.erase_records_atomically(
                    product_id=confirmation.preview.product_id,
                    expected_records=confirmation.preview.records,
                    receipt_request=transaction_request,
                )
            except Exception as exc:
                raise PersonalIntelligenceOwnershipError("exact primary-store deletion failed atomically") from exc
            remaining = _owned_records(
                await self.store.scan_product_records(product_id=confirmation.preview.product_id)
            )
            if remaining:
                raise PersonalIntelligenceOwnershipError(
                    "post-deletion primary-store probe found immutable Intelligence records"
                )
            return PersonalIntelligenceDeletionResult(
                proof=proof,
                transaction_receipt_ref=str(transaction.receipt_id),
            )

    async def _erase_derivatives(
        self,
        confirmation: PersonalIntelligenceDeleteConfirmationV1Alpha1,
    ) -> None:
        """Make the reviewed preview's derivative coverage true, or fail closed.

        Runs BEFORE the primary atomic erasure: derivative erasure is idempotent,
        so a failure here leaves every primary record (and the proof) unwritten,
        while a primary failure after this point is retried through a fresh
        preview whose counts honestly reflect the already-erased derivatives.
        """

        promised = confirmation.preview.derived_artifacts
        if not promised:
            return
        if self.derivatives is None:
            raise PersonalIntelligenceOwnershipError(
                "the reviewed preview promises derivative coverage but no erasure port is wired"
            )
        live = await self._derivative_coverage(product_id=confirmation.preview.product_id)
        if live != promised:
            raise PersonalIntelligenceDeletePreviewStale(
                "derivative artifacts changed after preview; request and review a new delete preview"
            )
        try:
            attested = await self.derivatives.erase_derivatives(
                product_id=confirmation.preview.product_id,
                coverage=promised,
            )
        except Exception as exc:
            raise PersonalIntelligenceOwnershipError(
                "derivative-artifact erasure failed closed before any primary record was removed"
            ) from exc
        if attested != derive_erasure_entries(promised):
            raise PersonalIntelligenceOwnershipError(
                "derivative-artifact erasure could not attest the reviewed preview's exact coverage"
            )

    @staticmethod
    def _proof(
        confirmation: PersonalIntelligenceDeleteConfirmationV1Alpha1,
    ) -> PersonalIntelligenceDeletionProofV1Alpha1:
        removal_material = {
            "preview": confirmation.preview.preview_digest,
            "confirmation": confirmation.confirmation_material_digest,
            "removed_count": confirmation.preview.record_count,
            "removed_record_set_digest": confirmation.preview.record_set_digest,
        }
        removal_evidence_digest = f"sha256:{canonical_hash(removal_material)}"
        return PersonalIntelligenceDeletionProofV1Alpha1(
            product_id=confirmation.preview.product_id,
            preview_ref=str(confirmation.preview.preview_id),
            confirmation_ref=str(confirmation.confirmation_id),
            removed_count=confirmation.preview.record_count,
            removed_record_set_digest=confirmation.preview.record_set_digest,
            removal_evidence_digest=removal_evidence_digest,
            completed_at=confirmation.confirmed_at,
            derived_artifact_erasure=derive_erasure_entries(confirmation.preview.derived_artifacts),
        )

    @staticmethod
    def _proof_record(proof: PersonalIntelligenceDeletionProofV1Alpha1) -> ImmutableRecordV1:
        return ImmutableRecordV1(
            product_id=proof.product_id,
            record_space=PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE,
            record_kind=PERSONAL_INTELLIGENCE_DELETION_PROOF_RECORD_KIND,
            record_key=str(proof.proof_id),
            payload_contract=proof.contract,
            payload=proof.model_dump(mode="json"),
            as_of=proof.completed_at,
            available_at=proof.completed_at,
            processing_order=0,
        )

    async def _prior_result(
        self,
        *,
        confirmation: PersonalIntelligenceDeleteConfirmationV1Alpha1,
        proof: PersonalIntelligenceDeletionProofV1Alpha1,
        proof_record: ImmutableRecordV1,
    ) -> PersonalIntelligenceDeletionResult | None:
        stored = await self.store.load_record(
            immutable_record_storage_id(
                product_id=proof.product_id,
                record_space=PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE,
                record_kind=PERSONAL_INTELLIGENCE_DELETION_PROOF_RECORD_KIND,
                record_key=str(proof.proof_id),
            ),
            product_id=proof.product_id,
            record_space=PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE,
            record_kind=PERSONAL_INTELLIGENCE_DELETION_PROOF_RECORD_KIND,
        )
        if stored is None:
            return None
        if stored != proof_record:
            raise PersonalIntelligenceOwnershipError("deletion proof identity already binds divergent material")
        receipt = await self.store.load_transaction_receipt(
            product_id=proof.product_id,
            record_space=PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE,
            transaction_key=str(confirmation.confirmation_id),
        )
        if receipt is None or receipt.records != (proof_record.reference(),):
            raise PersonalIntelligenceOwnershipError("stored deletion proof is missing its exact transaction receipt")
        return PersonalIntelligenceDeletionResult(
            proof=proof,
            transaction_receipt_ref=str(receipt.receipt_id),
        )


__all__ = [
    "PERSONAL_INTELLIGENCE_DELETION_PROOF_RECORD_KIND",
    "PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE",
    "PersonalIntelligenceDeletePreviewStale",
    "PersonalIntelligenceDeletionResult",
    "PersonalIntelligenceDerivativeErasurePort",
    "PersonalIntelligenceOwnershipError",
    "PersonalIntelligenceOwnershipAuthorizationPort",
    "PersonalIntelligenceOwnershipService",
    "PersonalIntelligenceOwnershipStore",
]
