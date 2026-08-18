"""Supported Core host for the governed claim-bound correction (J8) surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from ace.application import (
    RESOURCE_FEEDBACK_AUTHORITY,
    ClaimBoundCorrectionError,
    ClaimBoundCorrectionNotFound,
    ClaimBoundCorrectionService,
    ClaimCorrectionAdmissionV1Alpha1,
    ClaimCorrectionRequestV1Alpha1,
    IntelligenceResourceCorrectionIntent,
    IntelligenceResourceFeedbackDenied,
    IntelligenceResourceFeedbackError,
    IntelligenceResourceFeedbackService,
    IntelligenceResourceFeedbackUnavailable,
    IntelligenceResourceKind,
)
from ace.core import ImmutableRecordPersistenceError, ImmutableRecordStore
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    persist_task_authentication_receipt,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_resource_feedback import CoreIntelligenceResourceFeedbackTargets
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader


class ClaimCorrectionHttpReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: str
    product_id: str
    resource_kind: IntelligenceResourceKind
    resource_id: str
    resource_digest: str
    resource_contract: str
    revision: int
    as_of: datetime
    available_at: datetime


class ClaimCorrectionHttpRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    request_key: str = Field(min_length=1, max_length=240)
    target: ClaimCorrectionHttpReferenceV1
    claim_id: str = Field(min_length=1, max_length=240)
    citation_id: str = Field(min_length=1, max_length=240)
    correction_intent: IntelligenceResourceCorrectionIntent
    note: str = Field(min_length=1, max_length=3_800)
    evidence: tuple[ClaimCorrectionHttpReferenceV1, ...] = Field(default_factory=tuple, max_length=32)


@dataclass(frozen=True, slots=True)
class ClaimCorrectionHttpRuntime:
    records: ImmutableRecordStore
    authority: GovernedStateRuntimeUseResolver


class ClaimCorrectionHttpUnauthenticated(RuntimeError):
    pass


class ClaimCorrectionHttpDenied(RuntimeError):
    pass


class ClaimCorrectionHttpConflict(RuntimeError):
    pass


class ClaimCorrectionHttpUnavailable(RuntimeError):
    pass


def claim_bound_correction_runtime() -> ClaimCorrectionHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    return ClaimCorrectionHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=SurrealGovernedStateStore(pool)),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise ClaimCorrectionHttpUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or RESOURCE_FEEDBACK_AUTHORITY not in authorities:
        raise ClaimCorrectionHttpDenied("intelligence feedback authority is required")
    return actor_ref, product_id


async def correct_claim_bound_ask_answer(
    *,
    selector: ClaimCorrectionHttpRequestV1,
    user: dict,
    runtime: ClaimCorrectionHttpRuntime,
) -> ClaimCorrectionAdmissionV1Alpha1:
    actor_ref, product_id = _verified_claims(user)
    now = datetime.now(UTC)
    try:
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=now,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        request = ClaimCorrectionRequestV1Alpha1(
            authenticated_context=authentication.runtime_context(),
            product_id=product_id,
            authority_grant_ref=selector.authority_grant_ref,
            request_key=selector.request_key,
            target=selector.target.model_dump(mode="python"),
            claim_id=selector.claim_id,
            citation_id=selector.citation_id,
            correction_intent=selector.correction_intent,
            note=selector.note,
            evidence=tuple(item.model_dump(mode="python") for item in selector.evidence),
            requested_at=now,
        )
        # CoreIntelligenceResourceFeedbackTargets only reads authenticated_context/product_id/
        # authority_grant_ref off `request`, which ClaimCorrectionRequestV1Alpha1 also provides.
        targets = CoreIntelligenceResourceFeedbackTargets(
            reader=intelligence_resource_projection_reader(runtime.records),
            request=request,
        )
        service = ClaimBoundCorrectionService(
            targets=targets,
            feedback=IntelligenceResourceFeedbackService(
                records=runtime.records, targets=targets, authority=runtime.authority
            ),
        )
        return await service.correct(request, evaluated_at=now)
    except ClaimBoundCorrectionNotFound as exc:
        raise ClaimCorrectionHttpConflict(str(exc)) from exc
    except IntelligenceResourceFeedbackDenied as exc:
        raise ClaimCorrectionHttpDenied("current Core grant denied the correction") from exc
    except GovernedCompositionAuthorityError as exc:
        raise ClaimCorrectionHttpDenied("current Core grant denied the correction") from exc
    except ImmutableRecordPersistenceError as exc:
        raise ClaimCorrectionHttpUnavailable("correction evidence storage is unavailable") from exc
    except IntelligenceResourceFeedbackUnavailable as exc:
        raise ClaimCorrectionHttpUnavailable("correction evidence storage is unavailable") from exc
    except (ClaimBoundCorrectionError, IntelligenceResourceFeedbackError, TypeError, ValueError) as exc:
        raise ClaimCorrectionHttpConflict(str(exc)) from exc


__all__ = [
    "ClaimCorrectionHttpConflict",
    "ClaimCorrectionHttpDenied",
    "ClaimCorrectionHttpReferenceV1",
    "ClaimCorrectionHttpRequestV1",
    "ClaimCorrectionHttpRuntime",
    "ClaimCorrectionHttpUnauthenticated",
    "ClaimCorrectionHttpUnavailable",
    "claim_bound_correction_runtime",
    "correct_claim_bound_ask_answer",
]
