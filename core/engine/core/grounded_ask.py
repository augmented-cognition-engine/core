"""Supported Core host for the governed grounded Ask (J7) surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from ace.application import (
    RESOURCE_QUERY_AUTHORITY,
    AskAnswerV1Alpha1,
    AskNoAnswerV1Alpha1,
    AskQuestionV1Alpha1,
    GroundedAskError,
    GroundedAskService,
    IntelligenceResourcePlaneAuthorizationPort,
    IntelligenceResourcePlaneService,
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


class AskGroundedQuestionHttpRequestV1(BaseModel):
    """User material only; actor, product, and time come from the verified host."""

    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1, max_length=2_000)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    as_of: datetime
    available_at: datetime
    max_claims: int = Field(default=5, ge=1, le=20)


@dataclass(frozen=True, slots=True)
class AskGroundedQuestionHttpRuntime:
    records: ImmutableRecordStore
    authority: IntelligenceResourcePlaneAuthorizationPort


class AskGroundedQuestionHttpUnauthenticated(RuntimeError):
    pass


class AskGroundedQuestionHttpDenied(RuntimeError):
    pass


class AskGroundedQuestionHttpConflict(RuntimeError):
    pass


class AskGroundedQuestionHttpUnavailable(RuntimeError):
    pass


def ask_grounded_question_runtime() -> AskGroundedQuestionHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    return AskGroundedQuestionHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=SurrealGovernedStateStore(pool)),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise AskGroundedQuestionHttpUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or RESOURCE_QUERY_AUTHORITY not in authorities:
        raise AskGroundedQuestionHttpDenied("intelligence read authority is required")
    return actor_ref, product_id


async def ask_grounded_question(
    *,
    selector: AskGroundedQuestionHttpRequestV1,
    user: dict,
    runtime: AskGroundedQuestionHttpRuntime,
) -> AskAnswerV1Alpha1 | AskNoAnswerV1Alpha1:
    actor_ref, product_id = _verified_claims(user)
    now = datetime.now(UTC)
    try:
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=now,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        request = AskQuestionV1Alpha1(
            authenticated_context=authentication.runtime_context(),
            product_id=product_id,
            authority_grant_ref=selector.authority_grant_ref,
            question=selector.question,
            subject_refs=selector.subject_refs,
            as_of=selector.as_of,
            available_at=selector.available_at,
            max_claims=selector.max_claims,
        )
        resource_plane = IntelligenceResourcePlaneService(
            reader=intelligence_resource_projection_reader(runtime.records),
            authority=runtime.authority,
        )
        return await GroundedAskService(resource_plane=resource_plane).ask(request, evaluated_at=now)
    except GovernedCompositionAuthorityError as exc:
        raise AskGroundedQuestionHttpDenied("current Core grant denied the question") from exc
    except ImmutableRecordPersistenceError as exc:
        raise AskGroundedQuestionHttpUnavailable("authentication evidence is unavailable") from exc
    except (GroundedAskError, TypeError, ValueError) as exc:
        raise AskGroundedQuestionHttpConflict("ask request could not preserve its exact contract") from exc


__all__ = [
    "AskGroundedQuestionHttpConflict",
    "AskGroundedQuestionHttpDenied",
    "AskGroundedQuestionHttpRequestV1",
    "AskGroundedQuestionHttpRuntime",
    "AskGroundedQuestionHttpUnauthenticated",
    "AskGroundedQuestionHttpUnavailable",
    "ask_grounded_question",
    "ask_grounded_question_runtime",
]
