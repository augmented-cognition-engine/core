from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.core import GovernedStateHeadPreconditionV1Alpha1
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.intelligence_resources import (
    IntelligenceResourceHttpRuntime,
    intelligence_resource_runtime,
    router,
)
from core.engine.core.agent_composition_runtime import GovernedCompositionAuthorityError
from core.engine.core.auth import get_current_user

pytestmark = pytest.mark.unit

PRODUCT = "product:resource-http"
ACTOR = "principal:http-analyst"
GRANT = "authority_grant:resource-http-read"
NOW = datetime.now(UTC)


class _Authority:
    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.calls: list[dict] = []

    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
        self.calls.append(kwargs)
        if self.deny:
            raise GovernedCompositionAuthorityError("inactive grant")
        return AuthorityUseReceiptV1Alpha1(
            product_id=kwargs["context"].product_id,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref=kwargs["grant_ref"],
            grant_hash="b" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:resource-http",
                commit_receipt_id="authority_receipt:resource-http",
            ),
        )


def _claims(*, authorities: list[str] | None = None) -> dict:
    return {
        "sub": ACTOR,
        "product": PRODUCT,
        "authorities": ["observe_read"] if authorities is None else authorities,
        "exp": (NOW + timedelta(hours=1)).timestamp(),
    }


def _body() -> dict:
    return {
        "authority_grant_ref": GRANT,
        "resource_kinds": ["brief"],
        "subject_refs": [],
        "as_of": (NOW - timedelta(days=2)).isoformat(),
        "available_at": (NOW - timedelta(days=1)).isoformat(),
        "page_size": 20,
    }


async def _request(
    *,
    claims: dict,
    authority: _Authority,
    records: InMemoryImmutableRecordStore | None = None,
):
    app = FastAPI()
    app.include_router(router)
    records = records or InMemoryImmutableRecordStore()
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[intelligence_resource_runtime] = lambda: IntelligenceResourceHttpRuntime(
        records=records,
        authority=authority,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/intelligence/resources/query", json=_body())
    return response, records


@pytest.mark.asyncio
async def test_http_resource_query_derives_context_and_uses_current_core_authority() -> None:
    authority = _Authority()
    response, records = await _request(claims=_claims(), authority=authority)

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == PRODUCT
    assert body["actor_ref"] == ACTOR
    assert body["state"] == "complete"
    assert body["items"] == []
    assert body["authority_use"]["authority"] == "observe_read"
    assert body["authority_use"]["operation"] == "query_intelligence_resources"
    assert authority.calls[0]["context"].authentication_receipt_ref.startswith("task_authentication_receipt:")
    assert any(record.record_kind == "task_authentication" for record in records.records.values())


@pytest.mark.asyncio
async def test_http_resource_query_requires_token_and_current_grant_authority() -> None:
    response, records = await _request(claims=_claims(authorities=[]), authority=_Authority())
    assert response.status_code == 403
    assert records.records == {}

    denied, _ = await _request(claims=_claims(), authority=_Authority(deny=True))
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Intelligence query denied"


@pytest.mark.asyncio
async def test_http_resource_query_rejects_verified_claims_without_product_scope() -> None:
    claims = _claims()
    claims.pop("product")
    response, records = await _request(claims=claims, authority=_Authority())
    assert response.status_code == 401
    assert records.records == {}


@pytest.mark.asyncio
async def test_http_resource_query_reports_authentication_evidence_outage() -> None:
    response, _ = await _request(
        claims=_claims(),
        authority=_Authority(),
        records=InMemoryImmutableRecordStore(fail_after_records=1),
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Intelligence authentication evidence is unavailable"


def test_http_resource_query_openapi_exposes_the_public_page_contract() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/v1/intelligence/resources/query"]["post"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("IntelligenceResourcePageV1Alpha1")
