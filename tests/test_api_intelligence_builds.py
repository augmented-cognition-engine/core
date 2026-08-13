from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.core import GovernedStateHeadPreconditionV1Alpha1
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourcePageState,
    IntelligenceResourcePageV1Alpha1,
)
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.intelligence_builds import router
from core.engine.core.auth import get_current_user
from core.engine.core.intelligence_build import (
    AuthorizedIntelligenceBuild,
    IntelligenceBuildHttpRuntime,
    intelligence_build_runtime,
)

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)
PRODUCT = "product:personal-intelligence"
ACTOR = "principal:personal-analyst"
GRANT = "authority_grant:personal-intelligence-build"


def _receipt(*, build: AuthorizedIntelligenceBuild | None, kwargs: dict) -> AuthorityUseReceiptV1Alpha1:
    if build is None:
        context = kwargs["context"]
        subject_ref = kwargs["use_subject_ref"]
        subject_digest = kwargs["use_subject_digest"]
        operation = kwargs["operation"]
        authority = kwargs["authority"]
        grant_ref = kwargs["grant_ref"]
        evaluated_at = kwargs["evaluated_at"]
    else:
        context = build.authority_use.authenticated_context
        subject_ref = "intelligence_query:personal-first-picture"
        subject_digest = "sha256:" + "e" * 64
        operation = "query_intelligence_resources"
        authority = "observe_read"
        grant_ref = "authority_grant:personal-intelligence-read"
        evaluated_at = build.authority_use.evaluated_at
    return AuthorityUseReceiptV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authenticated_context=context,
        use_subject_ref=subject_ref,
        use_subject_digest=subject_digest,
        operation=operation,
        authority=authority,
        grant_ref=grant_ref,
        grant_hash="b" * 64,
        evaluated_at=evaluated_at,
        expires_at=NOW + timedelta(hours=1),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
            state_kind="authority_grant",
            product_id=PRODUCT,
            state_id=grant_ref,
            sequence=1,
            revision_id="authority_revision:personal-intelligence",
            commit_receipt_id="authority_receipt:personal-intelligence",
        ),
    )


class _Authority:
    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.calls: list[dict] = []

    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
        self.calls.append(kwargs)
        if self.deny:
            from core.engine.core.agent_composition_runtime import GovernedCompositionAuthorityError

            raise GovernedCompositionAuthorityError("inactive grant")
        return _receipt(build=None, kwargs=kwargs)


class _Executor:
    def __init__(self) -> None:
        self.builds: list[AuthorizedIntelligenceBuild] = []

    async def start(self, build: AuthorizedIntelligenceBuild) -> IntelligenceResourcePageV1Alpha1:
        self.builds.append(build)
        read_authority = _receipt(build=build, kwargs={})
        evaluated_at = read_authority.evaluated_at
        return IntelligenceResourcePageV1Alpha1(
            query_id=read_authority.use_subject_ref,
            query_digest=read_authority.use_subject_digest,
            product_id=PRODUCT,
            actor_ref=ACTOR,
            as_of=evaluated_at,
            available_at=evaluated_at,
            evaluated_at=evaluated_at,
            state=IntelligenceResourcePageState.COMPLETE,
            items=(),
            authority_use=read_authority,
        )


def _claims(*, authorities: list[str] | None = None) -> dict:
    return {
        "sub": ACTOR,
        "product": PRODUCT,
        "authorities": ["intelligence_build"] if authorities is None else authorities,
        "exp": (NOW + timedelta(hours=1)).timestamp(),
    }


def _body() -> dict:
    return {
        "authority_grant_ref": GRANT,
        "client_request_id": "atrium-request:first-picture",
        "profile_id": "profile:world-ai",
        "subject": "Keep me ahead of meaningful changes in artificial intelligence.",
        "outcome_id": "outcome:decision-readiness",
        "source_group_ids": ["sources:official", "sources:independent"],
        "cadence_id": "cadence:daily",
        "requested_at": NOW.isoformat(),
    }


async def _request(*, claims: dict, authority: _Authority, executor: _Executor):
    app = FastAPI()
    app.include_router(router)
    records = InMemoryImmutableRecordStore()
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[intelligence_build_runtime] = lambda: IntelligenceBuildHttpRuntime(
        records=records,
        authority=authority,
        executor=executor,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/intelligence/builds/start", json=_body())
    return response, records


@pytest.mark.asyncio
async def test_start_build_authorizes_exact_reviewed_plan_and_returns_resource_page() -> None:
    authority = _Authority()
    executor = _Executor()
    response, records = await _request(claims=_claims(), authority=authority, executor=executor)

    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "ace.http.intelligence-build-result/v1alpha1"
    assert body["product_id"] == PRODUCT
    assert body["actor_ref"] == ACTOR
    assert body["resource_page"]["state"] == "complete"
    assert executor.builds[0].request.subject == _body()["subject"]
    assert executor.builds[0].request.source_group_ids == ("sources:official", "sources:independent")
    assert authority.calls[0]["authority"] == "intelligence_build"
    assert authority.calls[0]["operation"] == "start_intelligence_build"
    assert any(record.record_kind == "task_authentication" for record in records.records.values())


@pytest.mark.asyncio
async def test_start_build_requires_build_authority_and_current_core_grant() -> None:
    denied_token, records = await _request(claims=_claims(authorities=[]), authority=_Authority(), executor=_Executor())
    assert denied_token.status_code == 403
    assert records.records == {}

    denied_grant, _ = await _request(claims=_claims(), authority=_Authority(deny=True), executor=_Executor())
    assert denied_grant.status_code == 403
    assert denied_grant.json()["detail"] == "Intelligence build denied"


def test_start_build_openapi_exposes_stable_request_and_result_contracts() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/v1/intelligence/builds/start"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("IntelligenceBuildStartV1")
    assert response_schema["$ref"].endswith("IntelligenceBuildResultV1")
