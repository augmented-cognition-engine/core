from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.intelligence_resource_plane import IntelligenceResourceProjectionBatch
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.intelligence_resources import router
from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_resource_feedback import (
    IntelligenceResourceFeedbackHttpRuntime,
    intelligence_resource_feedback_runtime,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:resource-feedback-http"
ACTOR = "principal:http-analyst"
GRANT = "authority_grant:resource-feedback-http"
NOW = datetime.now(UTC)


def _target() -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=PRODUCT,
        resource_kind=IntelligenceResourceKind.SHIFT,
        resource_id="shift:material-change",
        resource_digest="sha256:" + "a" * 64,
        resource_contract="ace.intelligence.shift/v1alpha1",
        revision=3,
        as_of=NOW - timedelta(days=1),
        available_at=NOW - timedelta(hours=1),
    )


class _Reader:
    async def read(self, **kwargs):
        return IntelligenceResourceProjectionBatch(
            records=(
                IntelligenceResourceRecordV1Alpha1(
                    reference=_target(),
                    availability=IntelligenceResourceAvailability.AVAILABLE,
                    title="Material change",
                ),
            )
        )


class _Authority:
    async def resolve_authority_use(self, **kwargs):
        return AuthorityUseReceiptV1Alpha1(
            product_id=PRODUCT,
            actor_ref=ACTOR,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref=GRANT,
            grant_hash="c" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:http-feedback",
                commit_receipt_id="authority_receipt:http-feedback",
            ),
        )


def _records() -> InMemoryImmutableRecordStore:
    return InMemoryImmutableRecordStore(
        governed_state_heads={
            ("authority_grant", PRODUCT, GRANT): GovernedStateHeadV1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:http-feedback",
                commit_receipt_id="authority_receipt:http-feedback",
                updated_at=NOW - timedelta(minutes=10),
            )
        }
    )


def _claims(*, authorities=None):
    return {
        "sub": ACTOR,
        "product": PRODUCT,
        "authorities": ["derive_propose"] if authorities is None else authorities,
        "exp": (NOW + timedelta(hours=1)).timestamp(),
    }


def _body():
    return {
        "authority_grant_ref": GRANT,
        "request_key": "feedback-request:http-1",
        "target": _target().model_dump(mode="json"),
        "correction_intent": "outdated",
        "note": "A newer filing changes the time-bound assessment.",
        "evidence": [],
    }


async def _request(monkeypatch, *, claims, body=None):
    monkeypatch.setattr(
        "core.engine.core.intelligence_resource_feedback.intelligence_resource_projection_reader",
        lambda records: _Reader(),
    )
    app = FastAPI()
    app.include_router(router)
    records = _records()
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[intelligence_resource_feedback_runtime] = lambda: IntelligenceResourceFeedbackHttpRuntime(
        records=records, authority=_Authority()
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/intelligence/resources/feedback", json=body or _body())
    return response, records


@pytest.mark.asyncio
async def test_http_records_exact_attributed_feedback(monkeypatch) -> None:
    response, records = await _request(monkeypatch, claims=_claims())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["feedback"]["request"]["target"] == _target().model_dump(mode="json")
    assert body["feedback"]["request"]["authenticated_context"]["actor_ref"] == ACTOR
    assert body["feedback"]["disposition"] == "recorded_proposal_only"
    assert body["feedback"]["changes_target"] is False
    assert body["feedback"]["changes_source_trust"] is False
    assert body["feedback"]["changes_ranking"] is False
    assert body["feedback"]["triggers_recalculation"] is False
    assert {record.record_kind for record in records.records.values()} == {
        "task_authentication",
        "resource_feedback",
    }


@pytest.mark.asyncio
async def test_http_requires_feedback_authority_before_writing(monkeypatch) -> None:
    response, records = await _request(monkeypatch, claims=_claims(authorities=[]))
    assert response.status_code == 403
    assert response.json()["detail"] == "Intelligence feedback denied"
    assert records.records == {}


@pytest.mark.asyncio
async def test_http_rejects_nonexistent_exact_digest(monkeypatch) -> None:
    body = _body()
    body["target"]["resource_digest"] = "sha256:" + "b" * 64
    response, records = await _request(monkeypatch, claims=_claims(), body=body)
    assert response.status_code == 409
    assert response.json()["detail"] == "Intelligence feedback could not preserve its exact contract"
    assert {record.record_kind for record in records.records.values()} == {"task_authentication"}


def test_feedback_openapi_exposes_exact_request_and_admission() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/v1/intelligence/resources/feedback"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "IntelligenceResourceFeedbackHttpRequestV1"
    )
    assert operation["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "IntelligenceResourceFeedbackAdmissionV1Alpha1"
    )
