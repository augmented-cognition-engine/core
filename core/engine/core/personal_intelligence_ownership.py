"""Authenticated host composition for personal Intelligence ownership."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ace.application import (
    PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE,
    PersonalIntelligenceDeletePreviewStale,
    PersonalIntelligenceDeletionResult,
    PersonalIntelligenceOwnershipError,
    PersonalIntelligenceOwnershipService,
)
from ace.application.agent_composition_runtime import TaskAuthenticationReceiptV1Alpha1
from ace.core import (
    AppendOnlyTransactionRequestV1,
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityClass,
    ImmutableRecordPersistenceError,
    ImmutableRecordStore,
    ImmutableRecordV1,
    PersonalIntelligenceDeleteConfirmationV1Alpha1,
    PersonalIntelligenceDeletePreviewRequestV1Alpha1,
    PersonalIntelligenceDeletePreviewV1Alpha1,
    PersonalIntelligenceDeletionProofV1Alpha1,
    PersonalIntelligenceExportArtifactV1Alpha1,
    PersonalIntelligenceExportRequestV1Alpha1,
    RuntimeUseResolver,
    canonical_hash,
)
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore

EXPORT_OPERATION = "export_personal_intelligence"
PREVIEW_DELETE_OPERATION = "preview_personal_intelligence_deletion"
CONFIRM_DELETE_OPERATION = "confirm_personal_intelligence_deletion"
OWNERSHIP_AUTHENTICATION_RECORD_KIND = "personal_intelligence_ownership_authentication"


class PersonalOwnershipHttpExportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)


class PersonalOwnershipHttpDeletePreviewV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    confirmation_window_seconds: int = Field(default=900, ge=60, le=3600)


class PersonalOwnershipHttpDeleteConfirmationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    preview: dict[str, Any]
    confirmation_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class PersonalOwnershipHttpDeletionResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proof: PersonalIntelligenceDeletionProofV1Alpha1
    transaction_receipt_ref: str


@dataclass(frozen=True, slots=True)
class PersonalOwnershipHttpRuntime:
    records: ImmutableRecordStore
    authority: RuntimeUseResolver


class PersonalOwnershipHttpUnauthenticated(RuntimeError):
    """The verified token lacks an exact personal product principal."""


class PersonalOwnershipHttpDenied(RuntimeError):
    """The verified token or current Core grant denied the operation."""


class PersonalOwnershipHttpUnavailable(RuntimeError):
    """Authentication evidence or primary immutable storage is unavailable."""


class PersonalOwnershipHttpConflict(RuntimeError):
    """The request is stale or could not preserve the ownership contract."""


def personal_ownership_runtime() -> PersonalOwnershipHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    return PersonalOwnershipHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=SurrealGovernedStateStore(pool)),
    )


def _verified_claims(user: dict, *, authority: AuthorityClass) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise PersonalOwnershipHttpUnauthenticated("verified token lacks personal product scope")
    if not isinstance(authorities, list) or authority.value not in authorities:
        raise PersonalOwnershipHttpDenied("verified token lacks personal ownership authority")
    return actor_ref, product_id


async def _authentication_context(
    *,
    user: dict,
    actor_ref: str,
    product_id: str,
    verified_at: datetime,
    records: ImmutableRecordStore,
) -> AuthenticatedRuntimeContextV1Alpha1:
    expires_claim = user.get("exp")
    if not isinstance(expires_claim, (int, float)) or isinstance(expires_claim, bool):
        raise PersonalOwnershipHttpUnauthenticated("verified token lacks an exact expiry")
    expires_at = datetime.fromtimestamp(expires_claim, tz=UTC)
    if expires_at <= verified_at:
        raise PersonalOwnershipHttpUnauthenticated("verified token expired before personal ownership authentication")
    receipt = TaskAuthenticationReceiptV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        verification_policy_ref="jwt_verification_policy:v1",
        authenticated_at=verified_at,
        expires_at=expires_at,
    )
    record = ImmutableRecordV1(
        product_id=product_id,
        record_space=PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE,
        record_kind=OWNERSHIP_AUTHENTICATION_RECORD_KIND,
        record_key=str(receipt.receipt_id),
        payload_contract=receipt.contract,
        payload=receipt.model_dump(mode="json"),
        as_of=verified_at,
        available_at=verified_at,
        processing_order=0,
    )
    await records.append(
        AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE,
            transaction_key=f"personal_ownership_authentication:{receipt.receipt_id}",
            records=(record,),
            submitted_at=verified_at,
        )
    )
    return receipt.runtime_context()


class _CurrentOwnershipAuthorization:
    def __init__(
        self,
        *,
        resolver: RuntimeUseResolver,
        grant_ref: str,
        token_authorities: tuple[str, ...],
    ) -> None:
        self.resolver = resolver
        self.grant_ref = grant_ref
        self.token_authorities = frozenset(token_authorities)

    async def authorize(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        operation: str,
        subject_ref: str,
        evaluated_at: datetime,
    ) -> None:
        required = (
            AuthorityClass.DELIVER_EXPORT if operation == EXPORT_OPERATION else AuthorityClass.ADMINISTER_LIFECYCLE
        )
        if required.value not in self.token_authorities:
            raise GovernedCompositionAuthorityError("token authority attenuation excludes personal ownership operation")
        subject_digest = f"sha256:{canonical_hash({'operation': operation, 'subject_ref': subject_ref})}"
        await self.resolver.resolve_authority_use(
            context=authenticated_context,
            use_subject_ref=subject_ref,
            use_subject_digest=subject_digest,
            operation=operation,
            authority=required.value,
            grant_ref=self.grant_ref,
            evaluated_at=evaluated_at,
        )


def _authorization_denied(exc: BaseException | None) -> bool:
    current = exc
    while current is not None:
        if isinstance(current, GovernedCompositionAuthorityError):
            return True
        current = current.__cause__
    return False


def _storage_unavailable(exc: BaseException | None) -> bool:
    current = exc
    while current is not None:
        if isinstance(current, ImmutableRecordPersistenceError):
            return True
        current = current.__cause__
    return False


async def _service(
    *,
    selector_grant_ref: str,
    user: dict,
    runtime: PersonalOwnershipHttpRuntime,
    authority: AuthorityClass,
    evaluated_at: datetime,
) -> tuple[PersonalIntelligenceOwnershipService, AuthenticatedRuntimeContextV1Alpha1]:
    actor_ref, product_id = _verified_claims(user, authority=authority)
    try:
        context = await _authentication_context(
            user=user,
            actor_ref=actor_ref,
            product_id=product_id,
            verified_at=evaluated_at,
            records=runtime.records,
        )
    except PersonalOwnershipHttpUnauthenticated:
        raise
    except ImmutableRecordPersistenceError as exc:
        raise PersonalOwnershipHttpUnavailable("personal ownership authentication evidence is unavailable") from exc
    return (
        PersonalIntelligenceOwnershipService(
            store=runtime.records,
            authorization=_CurrentOwnershipAuthorization(
                resolver=runtime.authority,
                grant_ref=selector_grant_ref,
                token_authorities=tuple(user.get("authorities", ())),
            ),
        ),
        context,
    )


def _raise_service_error(exc: PersonalIntelligenceOwnershipError) -> None:
    if _authorization_denied(exc):
        raise PersonalOwnershipHttpDenied("current Core grant denied personal ownership operation") from exc
    if _storage_unavailable(exc):
        raise PersonalOwnershipHttpUnavailable("personal ownership primary immutable storage is unavailable") from exc
    raise PersonalOwnershipHttpConflict("personal ownership request could not preserve its exact contract") from exc


async def export_personal_intelligence(
    *,
    selector: PersonalOwnershipHttpExportV1,
    user: dict,
    runtime: PersonalOwnershipHttpRuntime,
) -> PersonalIntelligenceExportArtifactV1Alpha1:
    now = datetime.now(UTC)
    service, context = await _service(
        selector_grant_ref=selector.authority_grant_ref,
        user=user,
        runtime=runtime,
        authority=AuthorityClass.DELIVER_EXPORT,
        evaluated_at=now,
    )
    try:
        return await service.export(
            PersonalIntelligenceExportRequestV1Alpha1(
                authenticated_context=context,
                requested_at=now,
            )
        )
    except PersonalIntelligenceOwnershipError as exc:
        _raise_service_error(exc)
    except (TypeError, ValueError) as exc:
        raise PersonalOwnershipHttpConflict("personal ownership export contract is invalid") from exc


async def preview_personal_intelligence_deletion(
    *,
    selector: PersonalOwnershipHttpDeletePreviewV1,
    user: dict,
    runtime: PersonalOwnershipHttpRuntime,
) -> PersonalIntelligenceDeletePreviewV1Alpha1:
    now = datetime.now(UTC)
    service, context = await _service(
        selector_grant_ref=selector.authority_grant_ref,
        user=user,
        runtime=runtime,
        authority=AuthorityClass.ADMINISTER_LIFECYCLE,
        evaluated_at=now,
    )
    expires_at = min(
        now + timedelta(seconds=selector.confirmation_window_seconds),
        context.expires_at,
    )
    try:
        return await service.preview_delete(
            PersonalIntelligenceDeletePreviewRequestV1Alpha1(
                authenticated_context=context,
                requested_at=now,
                expires_at=expires_at,
            )
        )
    except PersonalIntelligenceOwnershipError as exc:
        _raise_service_error(exc)
    except (TypeError, ValueError) as exc:
        raise PersonalOwnershipHttpConflict("personal ownership delete preview contract is invalid") from exc


async def confirm_personal_intelligence_deletion(
    *,
    selector: PersonalOwnershipHttpDeleteConfirmationV1,
    user: dict,
    runtime: PersonalOwnershipHttpRuntime,
) -> PersonalOwnershipHttpDeletionResultV1:
    now = datetime.now(UTC)
    service, context = await _service(
        selector_grant_ref=selector.authority_grant_ref,
        user=user,
        runtime=runtime,
        authority=AuthorityClass.ADMINISTER_LIFECYCLE,
        evaluated_at=now,
    )
    try:
        preview = PersonalIntelligenceDeletePreviewV1Alpha1.model_validate_json(json.dumps(selector.preview))
        result: PersonalIntelligenceDeletionResult = await service.confirm_delete(
            PersonalIntelligenceDeleteConfirmationV1Alpha1(
                authenticated_context=context,
                preview=preview,
                confirmation_digest=selector.confirmation_digest,
                confirmed_at=now,
            )
        )
        return PersonalOwnershipHttpDeletionResultV1(
            proof=result.proof,
            transaction_receipt_ref=result.transaction_receipt_ref,
        )
    except PersonalIntelligenceDeletePreviewStale as exc:
        raise PersonalOwnershipHttpConflict("personal ownership delete preview is stale") from exc
    except PersonalIntelligenceOwnershipError as exc:
        _raise_service_error(exc)
    except (TypeError, ValueError) as exc:
        raise PersonalOwnershipHttpConflict("personal ownership delete confirmation contract is invalid") from exc


__all__ = [
    "CONFIRM_DELETE_OPERATION",
    "EXPORT_OPERATION",
    "OWNERSHIP_AUTHENTICATION_RECORD_KIND",
    "PREVIEW_DELETE_OPERATION",
    "PersonalIntelligenceDeletePreviewV1Alpha1",
    "PersonalIntelligenceExportArtifactV1Alpha1",
    "PersonalOwnershipHttpConflict",
    "PersonalOwnershipHttpDeleteConfirmationV1",
    "PersonalOwnershipHttpDeletePreviewV1",
    "PersonalOwnershipHttpDeletionResultV1",
    "PersonalOwnershipHttpDenied",
    "PersonalOwnershipHttpExportV1",
    "PersonalOwnershipHttpRuntime",
    "PersonalOwnershipHttpUnauthenticated",
    "PersonalOwnershipHttpUnavailable",
    "confirm_personal_intelligence_deletion",
    "export_personal_intelligence",
    "personal_ownership_runtime",
    "preview_personal_intelligence_deletion",
]
