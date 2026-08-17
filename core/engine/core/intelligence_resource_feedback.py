"""Supported Core host for exact Intelligence-resource feedback writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from ace.application import (
    RESOURCE_FEEDBACK_AUTHORITY,
    IntelligenceResourceCorrectionIntent,
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceFeedbackAdmissionV1Alpha1,
    IntelligenceResourceFeedbackDenied,
    IntelligenceResourceFeedbackError,
    IntelligenceResourceFeedbackRequestV1Alpha1,
    IntelligenceResourceFeedbackService,
    IntelligenceResourceFeedbackUnavailable,
    IntelligenceResourceKind,
    IntelligenceResourceProjectionReader,
    IntelligenceResourceQueryV1Alpha1,
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
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader


class IntelligenceResourceFeedbackHttpReferenceV1(BaseModel):
    """JSON-wire form normalized before strict application validation."""

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


class IntelligenceResourceFeedbackHttpRequestV1(BaseModel):
    """User material only; actor, product, and time come from the verified host."""

    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    request_key: str = Field(min_length=1, max_length=240)
    target: IntelligenceResourceFeedbackHttpReferenceV1
    correction_intent: IntelligenceResourceCorrectionIntent
    note: str = Field(min_length=1, max_length=4_000)
    evidence: tuple[IntelligenceResourceFeedbackHttpReferenceV1, ...] = Field(default_factory=tuple, max_length=32)


@dataclass(frozen=True, slots=True)
class IntelligenceResourceFeedbackHttpRuntime:
    records: ImmutableRecordStore
    authority: GovernedStateRuntimeUseResolver


class IntelligenceResourceFeedbackHttpUnauthenticated(RuntimeError):
    pass


class IntelligenceResourceFeedbackHttpDenied(RuntimeError):
    pass


class IntelligenceResourceFeedbackHttpConflict(RuntimeError):
    pass


class IntelligenceResourceFeedbackHttpUnavailable(RuntimeError):
    pass


class CoreIntelligenceResourceFeedbackTargets:
    """Resolve exact public revisions through the established projection contributors."""

    def __init__(
        self, *, reader: IntelligenceResourceProjectionReader, request: IntelligenceResourceFeedbackRequestV1Alpha1
    ) -> None:
        self.reader = reader
        self.request = request

    async def load_exact(self, reference, *, evaluated_at: datetime):
        if reference.available_at > evaluated_at or reference.as_of > evaluated_at:
            return None
        cursor = None
        for _ in range(100):
            query = IntelligenceResourceQueryV1Alpha1(
                authenticated_context=self.request.authenticated_context,
                product_id=self.request.product_id,
                authority_grant_ref=self.request.authority_grant_ref,
                resource_kinds=(reference.resource_kind,),
                subject_refs=(),
                as_of=evaluated_at,
                available_at=evaluated_at,
                page_size=200,
                cursor=cursor,
            )
            batch = await self.reader.read(query=query, after=cursor, limit=201)
            for item in batch.records[:200]:
                if item.reference == reference:
                    return item
            if len(batch.records) <= 200:
                return None
            last = batch.records[199].reference
            cursor = IntelligenceResourceCursorV1Alpha1(
                query_id=str(query.query_id),
                after_available_at=last.available_at,
                after_resource_kind=last.resource_kind,
                after_resource_id=last.resource_id,
                after_revision=last.revision,
            )
        raise IntelligenceResourceFeedbackError("exact target lookup exceeded its bounded projection scan")


def intelligence_resource_feedback_runtime() -> IntelligenceResourceFeedbackHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    return IntelligenceResourceFeedbackHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=SurrealGovernedStateStore(pool)),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise IntelligenceResourceFeedbackHttpUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or RESOURCE_FEEDBACK_AUTHORITY not in authorities:
        raise IntelligenceResourceFeedbackHttpDenied("intelligence feedback authority is required")
    return actor_ref, product_id


async def submit_intelligence_resource_feedback(
    *,
    selector: IntelligenceResourceFeedbackHttpRequestV1,
    user: dict,
    runtime: IntelligenceResourceFeedbackHttpRuntime,
) -> IntelligenceResourceFeedbackAdmissionV1Alpha1:
    actor_ref, product_id = _verified_claims(user)
    now = datetime.now(UTC)
    try:
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=now,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        request = IntelligenceResourceFeedbackRequestV1Alpha1(
            authenticated_context=authentication.runtime_context(),
            product_id=product_id,
            authority_grant_ref=selector.authority_grant_ref,
            request_key=selector.request_key,
            target=selector.target.model_dump(mode="python"),
            correction_intent=selector.correction_intent,
            note=selector.note,
            evidence=tuple(item.model_dump(mode="python") for item in selector.evidence),
            requested_at=now,
        )
        targets = CoreIntelligenceResourceFeedbackTargets(
            reader=intelligence_resource_projection_reader(runtime.records),
            request=request,
        )
        return await IntelligenceResourceFeedbackService(
            records=runtime.records,
            targets=targets,
            authority=runtime.authority,
        ).submit(request, evaluated_at=now)
    except IntelligenceResourceFeedbackDenied as exc:
        raise IntelligenceResourceFeedbackHttpDenied("current Core grant denied feedback") from exc
    except GovernedCompositionAuthorityError as exc:
        raise IntelligenceResourceFeedbackHttpDenied("current Core grant denied feedback") from exc
    except ImmutableRecordPersistenceError as exc:
        raise IntelligenceResourceFeedbackHttpUnavailable("feedback evidence storage is unavailable") from exc
    except IntelligenceResourceFeedbackUnavailable as exc:
        raise IntelligenceResourceFeedbackHttpUnavailable("feedback evidence storage is unavailable") from exc
    except IntelligenceResourceFeedbackError as exc:
        raise IntelligenceResourceFeedbackHttpConflict(str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise IntelligenceResourceFeedbackHttpConflict(
            "feedback request could not preserve its exact contract"
        ) from exc


__all__ = [
    "IntelligenceResourceFeedbackHttpConflict",
    "IntelligenceResourceFeedbackHttpDenied",
    "IntelligenceResourceFeedbackHttpRequestV1",
    "IntelligenceResourceFeedbackHttpReferenceV1",
    "IntelligenceResourceFeedbackHttpRuntime",
    "IntelligenceResourceFeedbackHttpUnauthenticated",
    "IntelligenceResourceFeedbackHttpUnavailable",
    "intelligence_resource_feedback_runtime",
    "submit_intelligence_resource_feedback",
]
