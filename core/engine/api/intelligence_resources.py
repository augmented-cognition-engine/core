"""Governed HTTP adapter for the ACE Intelligence resource plane."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ace.application import (
    RESOURCE_QUERY_AUTHORITY,
    IntelligenceLedgerResourceProjectionReader,
    IntelligenceResourcePlaneAuthorizationPort,
    IntelligenceResourcePlaneError,
    IntelligenceResourcePlaneService,
)
from ace.core import ImmutableRecordPersistenceError, ImmutableRecordStore
from ace.intelligence import (
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourcePageV1Alpha1,
    IntelligenceResourceQueryV1Alpha1,
)
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    persist_task_authentication_receipt,
)
from core.engine.core.auth import get_current_user
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore

router = APIRouter(prefix="/v1/intelligence/resources", tags=["intelligence-resources"])


class IntelligenceResourceHttpQueryV1(BaseModel):
    """HTTP selector; authenticated context is derived from the verified bearer token."""

    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    resource_kinds: tuple[IntelligenceResourceKind, ...] = Field(min_length=1, max_length=32)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    as_of: datetime
    available_at: datetime
    page_size: int = Field(ge=1, le=200)
    cursor: IntelligenceResourceCursorV1Alpha1 | None = None


@dataclass(frozen=True, slots=True)
class IntelligenceResourceHttpRuntime:
    records: ImmutableRecordStore
    authority: IntelligenceResourcePlaneAuthorizationPort


def intelligence_resource_runtime() -> IntelligenceResourceHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    governed_state = SurrealGovernedStateStore(pool)
    return IntelligenceResourceHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=governed_state),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Verified token lacks product scope")
    if not isinstance(authorities, list) or RESOURCE_QUERY_AUTHORITY not in authorities:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Intelligence read authority is required")
    return actor_ref, product_id


@router.post("/query", response_model=IntelligenceResourcePageV1Alpha1)
async def query_intelligence_resources(
    selector: IntelligenceResourceHttpQueryV1,
    user: dict = Depends(get_current_user),
    runtime: IntelligenceResourceHttpRuntime = Depends(intelligence_resource_runtime),
) -> IntelligenceResourcePageV1Alpha1:
    """Reauthenticate and reauthorize one point-in-time page; cursors grant no authority."""

    actor_ref, product_id = _verified_claims(user)
    evaluated_at = datetime.now(UTC)
    try:
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=evaluated_at,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        request = IntelligenceResourceQueryV1Alpha1(
            authenticated_context=authentication.runtime_context(),
            product_id=product_id,
            authority_grant_ref=selector.authority_grant_ref,
            resource_kinds=selector.resource_kinds,
            subject_refs=selector.subject_refs,
            as_of=selector.as_of,
            available_at=selector.available_at,
            page_size=selector.page_size,
            cursor=selector.cursor,
        )
        return await IntelligenceResourcePlaneService(
            reader=IntelligenceLedgerResourceProjectionReader(store=runtime.records),
            authority=runtime.authority,
        ).query(request, evaluated_at=evaluated_at)
    except GovernedCompositionAuthorityError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Intelligence query denied") from exc
    except ImmutableRecordPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intelligence authentication evidence is unavailable",
        ) from exc
    except (IntelligenceResourcePlaneError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Intelligence resource query could not preserve its exact contract",
        ) from exc


__all__ = [
    "IntelligenceResourceHttpQueryV1",
    "IntelligenceResourceHttpRuntime",
    "intelligence_resource_runtime",
    "query_intelligence_resources",
    "router",
]
