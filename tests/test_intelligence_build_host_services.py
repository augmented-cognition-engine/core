from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ace.application.intelligence_build_execution import (
    REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
    IntelligenceBuildStartV1,
    ProductScopedImmutableRecordStore,
)
from ace.core import AppendOnlyTransactionRequestV1, ImmutableRecordScopeError, ImmutableRecordV1
from ace.testing import InMemoryImmutableRecordStore

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 13, 22, 0, tzinfo=UTC)
PRODUCT = "product:personal"


def _request(**changes) -> IntelligenceBuildStartV1:
    material = {
        "authority_grant_ref": "authority_grant:atrium-intelligence-build",
        "resource_authority_grant_ref": "authority_grant:atrium-observe-read",
        "client_request_id": "atrium-request:host-services",
        "profile_id": "intelligence_onboarding_profile:fixture",
        "subject": "Track the reviewed subject for meaningful material change.",
        "outcome_id": "decision_readiness",
        "source_group_ids": ("official_records",),
        "cadence_id": "daily_pulse",
        "approved_effects": REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
        "requested_at": NOW,
    }
    material.update(changes)
    return IntelligenceBuildStartV1(**material)


def test_reviewed_build_requires_the_exact_bounded_internal_effects() -> None:
    assert _request().approved_effects == REQUIRED_INTELLIGENCE_BUILD_EFFECTS
    with pytest.raises(ValidationError, match="exact bounded onboarding effect sequence"):
        _request(approved_effects=("connect_sources",))
    with pytest.raises(ValidationError):
        _request(approved_effects=(*REQUIRED_INTELLIGENCE_BUILD_EFFECTS, "publish_content"))


@pytest.mark.asyncio
async def test_invocation_store_enforces_the_authorized_product_fence() -> None:
    backing = InMemoryImmutableRecordStore()
    scoped = ProductScopedImmutableRecordStore(product_id=PRODUCT, store=backing)
    record = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="fixture",
        record_kind="brief",
        record_key="brief:one",
        payload_contract="fixture.brief/v1",
        payload={"title": "One"},
        as_of=NOW,
        available_at=NOW,
        processing_order=0,
    )
    request = AppendOnlyTransactionRequestV1(
        product_id=PRODUCT,
        record_space="fixture",
        transaction_key="fixture:one",
        records=(record,),
        submitted_at=NOW,
    )
    assert await scoped.append(request) == request.receipt()
    assert await scoped.scan_product_records(product_id=PRODUCT) == (record,)

    with pytest.raises(ImmutableRecordScopeError, match="authorized product"):
        await scoped.scan_product_records(product_id="product:other")
