"""Supported host composition for the governed Intelligence resource plane.

This is the only legacy Core host edge into the public ACE Application layer.
The HTTP adapter depends on this host boundary and never imports public ACE
packages directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from ace.application import (
    RESOURCE_QUERY_AUTHORITY,
    CompositeIntelligenceResourceProjectionReader,
    DecisionOutcomeFeedbackResourceProjectionReader,
    IntelligenceLedgerResourceProjectionReader,
    IntelligenceResourceCursorV1Alpha1,
    IntelligenceResourceKind,
    IntelligenceResourcePageV1Alpha1,
    IntelligenceResourcePlaneAuthorizationPort,
    IntelligenceResourcePlaneError,
    IntelligenceResourcePlaneService,
    IntelligenceResourceProjectionReader,
    IntelligenceResourceQueryV1Alpha1,
    LiveSourceResourceProjectionReader,
    MonitoringResourceProjectionReader,
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


class IntelligenceResourceHttpQueryV1(BaseModel):
    """HTTP selector; authenticated context comes only from verified claims."""

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


class IntelligenceResourceHttpDenied(RuntimeError):
    """The verified principal or current Core grant denied the query."""


class IntelligenceResourceHttpUnauthenticated(RuntimeError):
    """The verified token did not contain a usable product-scoped principal."""


class IntelligenceResourceHttpUnavailable(RuntimeError):
    """Required authentication evidence could not be persisted."""


class IntelligenceResourceHttpContractConflict(RuntimeError):
    """The query could not preserve the exact resource-plane contract."""


def intelligence_resource_runtime() -> IntelligenceResourceHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    governed_state = SurrealGovernedStateStore(pool)
    return IntelligenceResourceHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=governed_state),
    )


def intelligence_resource_projection_reader(records: ImmutableRecordStore) -> IntelligenceResourceProjectionReader:
    """Compose all disjoint rebuildable public projection contributors."""

    return CompositeIntelligenceResourceProjectionReader(
        IntelligenceLedgerResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        MonitoringResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        DecisionOutcomeFeedbackResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
        LiveSourceResourceProjectionReader(
            store=records,
            degrade_unsupported=False,
        ),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise IntelligenceResourceHttpUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or RESOURCE_QUERY_AUTHORITY not in authorities:
        raise IntelligenceResourceHttpDenied("intelligence read authority is required")
    return actor_ref, product_id


async def query_intelligence_resource_page(
    *,
    selector: IntelligenceResourceHttpQueryV1,
    user: dict,
    runtime: IntelligenceResourceHttpRuntime,
) -> IntelligenceResourcePageV1Alpha1:
    """Bind verified host context to one authorized public resource query."""

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
            reader=intelligence_resource_projection_reader(runtime.records),
            authority=runtime.authority,
        ).query(request, evaluated_at=evaluated_at)
    except GovernedCompositionAuthorityError as exc:
        raise IntelligenceResourceHttpDenied("current Core grant denied the query") from exc
    except ImmutableRecordPersistenceError as exc:
        raise IntelligenceResourceHttpUnavailable("authentication evidence is unavailable") from exc
    except (IntelligenceResourcePlaneError, TypeError, ValueError) as exc:
        raise IntelligenceResourceHttpContractConflict("resource query contract could not be preserved") from exc


__all__ = [
    "IntelligenceResourceHttpContractConflict",
    "IntelligenceResourceHttpDenied",
    "IntelligenceResourceHttpQueryV1",
    "IntelligenceResourceHttpRuntime",
    "IntelligenceResourceHttpUnauthenticated",
    "IntelligenceResourceHttpUnavailable",
    "IntelligenceResourcePageV1Alpha1",
    "intelligence_resource_projection_reader",
    "intelligence_resource_runtime",
    "query_intelligence_resource_page",
]
