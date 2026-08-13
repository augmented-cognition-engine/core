"""Public, domain-neutral contract for trusted Intelligence build executors.

Core authorizes an exact onboarding request before handing this material to an
installed executor. Executors may interpret only the profile they declare and
must return a product- and actor-scoped Intelligence resource page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ace.application.intelligence_resource_plane import (
    IntelligenceResourceKind,
    IntelligenceResourcePageV1Alpha1,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordScopeError,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1

IntelligenceBuildEffect = Literal[
    "connect_sources",
    "map_concepts",
    "activate_watch",
    "create_first_brief",
]
REQUIRED_INTELLIGENCE_BUILD_EFFECTS: tuple[IntelligenceBuildEffect, ...] = (
    "connect_sources",
    "map_concepts",
    "activate_watch",
    "create_first_brief",
)


class IntelligenceBuildStartV1(BaseModel):
    """One reviewed Atrium plan submitted for governed execution."""

    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    resource_authority_grant_ref: str = Field(min_length=1, max_length=240)
    client_request_id: str = Field(min_length=1, max_length=240)
    profile_id: str = Field(min_length=1, max_length=240)
    subject: str = Field(min_length=8, max_length=2_000)
    outcome_id: str = Field(min_length=1, max_length=240)
    source_group_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=64)
    cadence_id: str = Field(min_length=1, max_length=240)
    approved_effects: tuple[IntelligenceBuildEffect, ...]
    requested_at: datetime

    @field_validator("source_group_ids")
    @classmethod
    def _unique_source_groups(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("source_group_ids must be unique")
        return value

    @field_validator("approved_effects")
    @classmethod
    def _exact_bounded_effects(cls, value: tuple[IntelligenceBuildEffect, ...]) -> tuple[IntelligenceBuildEffect, ...]:
        if value != REQUIRED_INTELLIGENCE_BUILD_EFFECTS:
            raise ValueError("approved_effects must preserve the exact bounded onboarding effect sequence")
        return value


@dataclass(frozen=True, slots=True)
class AuthorizedIntelligenceBuild:
    """Exact identity, scope, request, and authority admitted by Core."""

    build_id: str
    request_digest: str
    product_id: str
    actor_ref: str
    request: IntelligenceBuildStartV1
    authority_use: AuthorityUseReceiptV1Alpha1


class ProductScopedImmutableRecordStore:
    """Restrict every public immutable-record operation to one product fence."""

    def __init__(self, *, product_id: str, store: ImmutableRecordStore) -> None:
        self.product_id = product_id
        self._store = store

    def _check(self, product_id: str) -> None:
        if product_id != self.product_id:
            raise ImmutableRecordScopeError("Intelligence build store crossed its authorized product scope")

    async def append(self, request: AppendOnlyTransactionRequestV1) -> AppendOnlyTransactionReceiptV1:
        self._check(request.product_id)
        return await self._store.append(request)

    async def load_record(self, storage_id: str, *, product_id: str, record_space: str, record_kind: str):
        self._check(product_id)
        return await self._store.load_record(
            storage_id,
            product_id=product_id,
            record_space=record_space,
            record_kind=record_kind,
        )

    async def load_transaction_receipt(self, *, product_id: str, record_space: str, transaction_key: str):
        self._check(product_id)
        return await self._store.load_transaction_receipt(
            product_id=product_id,
            record_space=record_space,
            transaction_key=transaction_key,
        )

    async def read_as_of(
        self, *, product_id: str, record_space: str, record_kind: str, available_at: datetime
    ) -> tuple[ImmutableRecordV1, ...]:
        self._check(product_id)
        return await self._store.read_as_of(
            product_id=product_id,
            record_space=record_space,
            record_kind=record_kind,
            available_at=available_at,
        )

    async def count_as_of(self, *, product_id: str, record_space: str, record_kind: str, available_at: datetime) -> int:
        self._check(product_id)
        return await self._store.count_as_of(
            product_id=product_id,
            record_space=record_space,
            record_kind=record_kind,
            available_at=available_at,
        )

    async def scan_product_records(self, *, product_id: str) -> tuple[ImmutableRecordV1, ...]:
        self._check(product_id)
        return await self._store.scan_product_records(product_id=product_id)


class IntelligenceBuildResourcePagePort(Protocol):
    """Core-owned projection and read-authority boundary for one authorized build."""

    async def query(
        self,
        *,
        resource_kinds: tuple[IntelligenceResourceKind, ...],
        subject_refs: tuple[str, ...],
        as_of: datetime,
        available_at: datetime,
        evaluated_at: datetime,
        page_size: int = 200,
    ) -> IntelligenceResourcePageV1Alpha1: ...


@dataclass(frozen=True, slots=True)
class IntelligenceBuildHostServices:
    """Invocation-scoped capabilities Core grants to one trusted executor."""

    records: ImmutableRecordStore
    resources: IntelligenceBuildResourcePagePort


class IntelligenceBuildExecutor(Protocol):
    """Trusted executable adapter for one or more exact onboarding profiles."""

    async def start(
        self, build: AuthorizedIntelligenceBuild, host_services: IntelligenceBuildHostServices
    ) -> IntelligenceResourcePageV1Alpha1: ...


__all__ = [
    "AuthorizedIntelligenceBuild",
    "IntelligenceBuildEffect",
    "IntelligenceBuildExecutor",
    "IntelligenceBuildHostServices",
    "IntelligenceBuildResourcePagePort",
    "IntelligenceBuildStartV1",
    "ProductScopedImmutableRecordStore",
    "REQUIRED_INTELLIGENCE_BUILD_EFFECTS",
]
