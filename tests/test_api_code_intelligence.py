from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from git import Repo
from httpx import ASGITransport, AsyncClient

from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.testing import InMemoryImmutableRecordStore
from core.engine.core.agent_composition_runtime import GovernedCompositionAuthorityError


@pytest.mark.asyncio
async def test_atrium_code_journey_requires_authentication() -> None:
    from core.engine.api.main import app
    from core.engine.core.auth import get_header_current_user

    app.dependency_overrides.pop(get_header_current_user, None)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/code-intelligence/journey",
            json={"query": "Inspect authentication", "target_path": "pkg/service.py"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repository_configured", "configured_product", "principal", "expected_status", "expected_detail"),
    [
        (
            False,
            "product:test",
            {"sub": "user:test", "product": "product:test"},
            503,
            "Code Intelligence repository inspection is not configured.",
        ),
        (
            True,
            "",
            {"sub": "user:test", "product": "product:test"},
            503,
            "Code Intelligence product inspection is not configured.",
        ),
        (
            True,
            "product:test",
            {"sub": "user:test"},
            401,
            "Verified token lacks product scope",
        ),
        (
            True,
            "product:test",
            {"sub": "user:test", "product": "product:other"},
            403,
            "Code Intelligence repository inspection is not available for this product.",
        ),
    ],
)
async def test_atrium_code_journey_fails_before_repository_or_cache_access(
    tmp_path: Path,
    monkeypatch,
    repository_configured: bool,
    configured_product: str,
    principal: dict,
    expected_status: int,
    expected_detail: str,
) -> None:
    from fastapi import FastAPI

    import core.engine.api.code_intelligence as code_api
    from core.engine.core.auth import get_header_current_user
    from core.engine.core.config import settings

    repository = _repository(tmp_path)
    index_store = tmp_path / "index-store"
    monkeypatch.setattr(
        settings,
        "code_intelligence_repository_root",
        str(repository) if repository_configured else "",
    )
    monkeypatch.setattr(settings, "code_intelligence_product_ref", configured_product)
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(index_store))
    accessed: list[str] = []

    def _unexpected_journey(*_args, **_kwargs):
        accessed.append("repository")
        raise AssertionError("repository inspection must not start")

    def _unexpected_store(*_args, **_kwargs):
        accessed.append("cache")
        raise AssertionError("local cache must not initialize")

    monkeypatch.setattr(code_api, "CodeIntelligenceJourney", _unexpected_journey)
    monkeypatch.setattr(code_api, "_store_for", _unexpected_store)
    app = FastAPI()
    app.include_router(code_api.router)
    app.dependency_overrides[get_header_current_user] = lambda: principal
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/code-intelligence/journey",
            json={"query": "Inspect product isolation", "target_path": "pkg/service.py"},
        )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    if expected_status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    assert accessed == []
    assert not index_store.exists()


@pytest.mark.asyncio
async def test_atrium_code_journey_rejects_valid_query_token_before_repository_or_cache_access(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from fastapi import FastAPI

    import core.engine.api.code_intelligence as code_api
    from core.engine.core.auth import create_access_token
    from core.engine.core.config import settings

    repository = _repository(tmp_path)
    index_store = tmp_path / "index-store"
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(repository))
    monkeypatch.setattr(settings, "code_intelligence_product_ref", "product:test")
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(index_store))
    accessed: list[str] = []

    def _unexpected_journey(*_args, **_kwargs):
        accessed.append("repository")
        raise AssertionError("repository inspection must not start")

    def _unexpected_store(*_args, **_kwargs):
        accessed.append("cache")
        raise AssertionError("local cache must not initialize")

    monkeypatch.setattr(code_api, "CodeIntelligenceJourney", _unexpected_journey)
    monkeypatch.setattr(code_api, "_store_for", _unexpected_store)
    token = create_access_token({"sub": "user:test", "product": "product:test"})
    app = FastAPI()
    app.include_router(code_api.router)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/code-intelligence/journey",
            params={"token": token},
            json={"query": "Inspect header boundary", "target_path": "pkg/service.py"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert accessed == []
    assert not index_store.exists()


def _precondition(body: dict) -> dict:
    """Externalize the exact coordinate triple a caller must hold and resupply."""

    return {
        "expected_snapshot_id": body["index_snapshot_id"],
        "expected_snapshot_digest": body["index_snapshot_digest"],
        "expected_snapshot_generation": body["index_generation"],
    }


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pkg" / "service.py").write_text("def used() -> int:\n    return 1\n", encoding="utf-8")
    (root / "pkg" / "consumer.py").write_text(
        "from pkg.service import used\n\ndef call() -> int:\n    return used()\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_service.py").write_text(
        "from pkg.service import used\n\ndef test_used():\n    assert used() == 1\n",
        encoding="utf-8",
    )
    repo = Repo.init(root)
    repo.index.add(["pkg/service.py", "pkg/consumer.py", "tests/test_service.py"])
    repo.index.commit("initial")
    return root


def test_code_intelligence_openapi_freezes_effects_and_failure_statuses() -> None:
    from fastapi import FastAPI

    from core.engine.api.code_intelligence import router

    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    journey = schema["paths"]["/v1/code-intelligence/journey"]["post"]
    admission = schema["paths"]["/v1/code-intelligence/admissions"]["post"]
    assert set(journey["responses"]) == {"200", "401", "403", "409", "422", "503"}
    assert set(admission["responses"]) == {"200", "401", "403", "409", "422", "503"}

    models = schema["components"]["schemas"]
    journey_fields = models["AtriumCodeJourneyResponse"]["properties"]
    assert "read_only" not in journey_fields
    assert journey_fields["contract"]["const"] == "ace.code-intelligence.atrium-journey-response/v1alpha1"
    assert journey_fields["repository_read_only"]["const"] is True
    assert journey_fields["product_history_write"]["const"] is False
    assert journey_fields["local_cache_may_write"]["const"] is True
    assert journey_fields["index_store_provider_free"]["const"] is True
    assert journey_fields["index_snapshot_is_product_truth"]["const"] is False
    assert journey_fields["index_snapshot_id"]["pattern"] == r"^code_index_snapshot:[a-f0-9]{32}$"
    assert journey_fields["index_snapshot_digest"]["pattern"] == r"^sha256:[a-f0-9]{64}$"
    assert journey_fields["index_generation"]["minimum"] == 1
    assert journey_fields["index_generation"]["maximum"] == 1_000_000_000

    request_fields = models["CodeIntelligenceJourneyRequest"]["properties"]
    admission_request_fields = models["CodeIntelligenceAdmissionRequest"]["properties"]
    for fields in (request_fields, admission_request_fields):
        supplied = fields["expected_snapshot_id"]["anyOf"][0]
        assert supplied["pattern"] == r"^code_index_snapshot:[a-f0-9]{32}$"
        assert fields["expected_snapshot_digest"]["anyOf"][0]["pattern"] == r"^sha256:[a-f0-9]{64}$"
        generation = fields["expected_snapshot_generation"]["anyOf"][0]
        assert generation["type"] == "integer"
        assert generation["minimum"] == 1
        assert generation["maximum"] == 1_000_000_000
        assert {"type": "null"} in fields["expected_snapshot_id"]["anyOf"]

    admission_fields = models["AtriumCodeLensAdmissionResponse"]["properties"]
    assert admission_fields["contract"]["const"] == (
        "ace.code-intelligence.atrium-code-lens-admission-response/v1alpha1"
    )


# ---------------------------------------------------------------------------
# expected_snapshot_generation must be an exact Python/JSON integer.  Pydantic's
# default "lax" int coercion would otherwise accept bool, numeric strings,
# integral floats, and Decimal — silently reinterpreting caller-held external
# continuity evidence as a different exact value than the caller supplied.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_generation",
    [
        True,
        False,
        "1",
        "1000000000",
        1.0,
        1_000_000_000.0,
        1.5,
        Decimal("1"),
        Decimal("1.5"),
        0,
        -1,
        1_000_000_001,
    ],
)
def test_expected_snapshot_generation_rejects_non_exact_values(invalid_generation) -> None:
    from pydantic import ValidationError

    from core.engine.api.code_intelligence import CodeIntelligenceJourneyRequest

    with pytest.raises(ValidationError):
        CodeIntelligenceJourneyRequest(
            query="Inspect generation typing",
            target_path="pkg/service.py",
            expected_snapshot_id="code_index_snapshot:" + "a" * 32,
            expected_snapshot_digest="sha256:" + "b" * 64,
            expected_snapshot_generation=invalid_generation,
        )


@pytest.mark.parametrize("valid_generation", [1, 42, 1_000_000_000])
def test_expected_snapshot_generation_accepts_exact_python_integers(valid_generation: int) -> None:
    from core.engine.api.code_intelligence import CodeIntelligenceJourneyRequest

    body = CodeIntelligenceJourneyRequest(
        query="Inspect generation typing",
        target_path="pkg/service.py",
        expected_snapshot_id="code_index_snapshot:" + "a" * 32,
        expected_snapshot_digest="sha256:" + "b" * 64,
        expected_snapshot_generation=valid_generation,
    )

    assert body.expected_snapshot_generation == valid_generation
    assert type(body.expected_snapshot_generation) is int


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_generation",
    [True, False, "1", 1.0, 1.5],
)
async def test_atrium_code_journey_rejects_non_exact_generation_over_http(
    tmp_path: Path,
    monkeypatch,
    invalid_generation,
) -> None:
    app, _root, store_root = _journey_app(tmp_path, monkeypatch)

    response = await _journey(
        app,
        expected_snapshot_id="code_index_snapshot:" + "a" * 32,
        expected_snapshot_digest="sha256:" + "b" * 64,
        expected_snapshot_generation=invalid_generation,
    )

    assert response.status_code == 422
    assert not any(store_root.rglob("snapshot-*.json"))


ADMISSION_PRODUCT = "product:code-admission"
ADMISSION_ACTOR = "principal:code-operator"
ADMISSION_GRANT = "authority_grant:code-admission"


def _admission_head(now: datetime) -> GovernedStateHeadV1:
    return GovernedStateHeadV1(
        state_kind="authority_grant",
        product_id=ADMISSION_PRODUCT,
        state_id=ADMISSION_GRANT,
        sequence=1,
        revision_id="authority_revision:code-admission",
        commit_receipt_id="authority_receipt:code-admission",
        updated_at=now - timedelta(minutes=5),
    )


class _AdmissionAuthority:
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
            expires_at=kwargs["evaluated_at"] + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(
                _admission_head(kwargs["evaluated_at"])
            ),
        )


def _admission_claims(*, authorities: list[str] | None = None) -> dict:
    return {
        "sub": ADMISSION_ACTOR,
        "product": ADMISSION_PRODUCT,
        "authorities": ["mutate_internal"] if authorities is None else authorities,
        "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
    }


def _admission_body() -> dict:
    return {
        "query": "What breaks if used changes?",
        "target_path": "pkg/service.py",
        "receiver_ref": "coding-agent:test",
        "authority_grant_ref": ADMISSION_GRANT,
    }


def _admission_store(*, fail_after_records: int | None = None) -> InMemoryImmutableRecordStore:
    store = InMemoryImmutableRecordStore(fail_after_records=fail_after_records)
    store.set_governed_state_head(_admission_head(datetime.now(UTC)))
    return store


async def _admission_request(
    *,
    tmp_path: Path,
    monkeypatch,
    claims: dict | None,
    authority: _AdmissionAuthority,
    records: InMemoryImmutableRecordStore | None = None,
    body: dict | None = None,
    repository_ref: str = "repository:configured-code-admission",
    prewarm_journey: bool = False,
    repetitions: int = 1,
    auth_transport: str = "override",
):
    from fastapi import FastAPI

    from core.engine.api.code_intelligence import router
    from core.engine.code_intelligence.resource_plane import (
        AtriumCodeLensAdmissionHttpRuntime,
        atrium_code_lens_admission_runtime,
    )
    from core.engine.core.auth import create_access_token, get_current_user, get_header_current_user
    from core.engine.core.config import settings

    root = _repository(tmp_path)
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(root))
    monkeypatch.setattr(settings, "code_intelligence_product_ref", ADMISSION_PRODUCT)
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(tmp_path / "index-store"))
    monkeypatch.setattr(settings, "code_intelligence_repository_ref", repository_ref)
    app = FastAPI()
    app.include_router(router)
    records = records or _admission_store()
    request_headers = {}
    request_params = {}
    if claims is not None and auth_transport == "override":
        app.dependency_overrides[get_current_user] = lambda: claims
        app.dependency_overrides[get_header_current_user] = lambda: claims
    elif claims is not None:
        token = create_access_token(claims)
        if auth_transport == "header":
            request_headers["Authorization"] = f"Bearer {token}"
        elif auth_transport == "query":
            request_params["token"] = token
        else:
            raise ValueError(f"unsupported auth transport: {auth_transport}")
    app.dependency_overrides[atrium_code_lens_admission_runtime] = lambda: AtriumCodeLensAdmissionHttpRuntime(
        records=records,
        authority=authority,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        admission_body = body or _admission_body()
        if prewarm_journey:
            journey_response = await client.post(
                "/v1/code-intelligence/journey",
                json={"query": "What breaks if used changes?", "target_path": "pkg/service.py"},
                headers=request_headers,
                params=request_params,
            )
            assert journey_response.status_code == 200
            # Admission inherits the journey's request contract, so a cache the
            # journey already warmed must be reopened through the same exact
            # externally held coordinates.
            admission_body = {**admission_body, **_precondition(journey_response.json())}
        responses = []
        for _ in range(repetitions):
            responses.append(
                await client.post(
                    "/v1/code-intelligence/admissions",
                    json=admission_body,
                    headers=request_headers,
                    params=request_params,
                )
            )
    response = responses[0] if repetitions == 1 else tuple(responses)
    return response, records, tmp_path / "index-store"


@pytest.mark.asyncio
async def test_atrium_code_journey_is_authenticated_bounded_and_body_free(tmp_path: Path, monkeypatch) -> None:
    from core.engine.api.main import app
    from core.engine.core.auth import get_header_current_user
    from core.engine.core.config import settings

    root = _repository(tmp_path)
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(root))
    monkeypatch.setattr(settings, "code_intelligence_product_ref", "product:test")
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(tmp_path / "index-store"))
    app.dependency_overrides[get_header_current_user] = lambda: {
        "sub": "user:test",
        "product": "product:test",
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/code-intelligence/journey",
                json={
                    "query": "What breaks if used changes?",
                    "target_path": "pkg/service.py",
                    "receiver_ref": "coding-agent:test",
                },
            )
    finally:
        app.dependency_overrides.pop(get_header_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["lens"]["impact"]["direct_dependents"] == ["pkg/consumer.py", "tests/test_service.py"]
    assert body["context_bodies_exposed"] is False
    assert body["repository_read_only"] is True
    assert body["product_history_write"] is False
    assert body["local_cache_may_write"] is True
    assert "blocks" not in body
    assert body["manifest"]["blocks"]
    assert all("body" not in receipt for receipt in body["manifest"]["blocks"])
    assert body["handoff"]["grants_effect_authority"] is False
    assert body["index_generation"] == 1
    assert body["index_reopened"] is False
    assert body["index_store_provider_free"] is True
    assert body["index_snapshot_is_product_truth"] is False
    assert body["index_snapshot_digest"].startswith("sha256:")

    app.dependency_overrides[get_header_current_user] = lambda: {
        "sub": "user:test",
        "product": "product:test",
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            reopened = await client.post(
                "/v1/code-intelligence/journey",
                json={
                    "query": "What breaks if used changes?",
                    "target_path": "pkg/service.py",
                    **_precondition(body),
                },
            )
    finally:
        app.dependency_overrides.pop(get_header_current_user, None)
    assert reopened.status_code == 200
    assert reopened.json()["index_reopened"] is True
    assert reopened.json()["index_snapshot_id"] == body["index_snapshot_id"]
    assert reopened.json()["index_snapshot_digest"] == body["index_snapshot_digest"]
    assert reopened.json()["index_generation"] == 1

    (root / "pkg" / "service.py").write_text(
        "def used() -> int:\n    return 1\n\ndef newly_observed() -> int:\n    return 2\n",
        encoding="utf-8",
    )
    app.dependency_overrides[get_header_current_user] = lambda: {
        "sub": "user:test",
        "product": "product:test",
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            updated = await client.post(
                "/v1/code-intelligence/journey",
                json={
                    "query": "What breaks if used changes?",
                    "target_path": "pkg/service.py",
                    **_precondition(body),
                },
            )
    finally:
        app.dependency_overrides.pop(get_header_current_user, None)
    assert updated.status_code == 200
    assert updated.json()["index_generation"] == 2
    assert updated.json()["index_reopened"] is False
    assert updated.json()["index_snapshot_id"] != body["index_snapshot_id"]


@pytest.mark.asyncio
async def test_atrium_code_journey_rejects_path_escape(tmp_path: Path, monkeypatch) -> None:
    from core.engine.api.main import app
    from core.engine.core.auth import get_header_current_user
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(_repository(tmp_path)))
    monkeypatch.setattr(settings, "code_intelligence_product_ref", "product:test")
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(tmp_path / "index-store"))
    app.dependency_overrides[get_header_current_user] = lambda: {
        "sub": "user:test",
        "product": "product:test",
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/code-intelligence/journey",
                json={"query": "Inspect escape", "target_path": "../outside.py"},
            )
    finally:
        app.dependency_overrides.pop(get_header_current_user, None)

    assert response.status_code == 422
    assert "escapes repository" in response.json()["detail"]


@pytest.mark.asyncio
async def test_atrium_code_journey_never_dispatches_governed_admission(tmp_path: Path, monkeypatch) -> None:
    from fastapi import FastAPI

    from core.engine.api.code_intelligence import router
    from core.engine.code_intelligence.resource_plane import atrium_code_lens_admission_runtime
    from core.engine.core.auth import get_header_current_user
    from core.engine.core.config import settings

    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(_repository(tmp_path)))
    monkeypatch.setattr(settings, "code_intelligence_product_ref", ADMISSION_PRODUCT)
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(tmp_path / "index-store"))
    monkeypatch.setattr(settings, "code_intelligence_repository_ref", "repository:must-not-be-admitted")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_header_current_user] = lambda: {
        "sub": ADMISSION_ACTOR,
        "product": ADMISSION_PRODUCT,
    }

    def _unexpected_admission_runtime():
        raise AssertionError("read-only journey initialized governed admission persistence")

    app.dependency_overrides[atrium_code_lens_admission_runtime] = _unexpected_admission_runtime
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/code-intelligence/journey",
            json={"query": "What breaks if used changes?", "target_path": "pkg/service.py"},
        )

    assert response.status_code == 200
    assert response.json()["repository_read_only"] is True
    assert response.json()["product_history_write"] is False
    assert response.json()["local_cache_may_write"] is True
    assert (tmp_path / "index-store").exists()


def test_atrium_code_journey_rejects_repository_change_after_snapshot_reopen(tmp_path: Path, monkeypatch) -> None:
    import core.engine.api.code_intelligence as code_api
    from core.engine.core.config import settings

    root = _repository(tmp_path)
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(root))
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(tmp_path / "index-store"))
    request = code_api.CodeIntelligenceJourneyRequest(
        query="What breaks if used changes?",
        target_path="pkg/service.py",
    )
    first = code_api._prepare_code_journey(request)
    reopen_request = code_api.CodeIntelligenceJourneyRequest(
        query="What breaks if used changes?",
        target_path="pkg/service.py",
        expected_snapshot_id=first.snapshot.snapshot_id,
        expected_snapshot_digest=first.snapshot.snapshot_digest,
        expected_snapshot_generation=first.snapshot.generation,
    )
    original = code_api._reopened_index

    def _reopen_then_mutate(journey, store, precondition):
        reopened = original(journey, store, precondition)
        (root / "pkg" / "service.py").write_text(
            "def used() -> int:\n    return 2\n",
            encoding="utf-8",
        )
        return reopened

    monkeypatch.setattr(code_api, "_reopened_index", _reopen_then_mutate)
    with pytest.raises(ValueError, match="changed after the exact index snapshot was reopened"):
        code_api._prepare_code_journey(reopen_request)

    snapshots = code_api._store_for(root).list_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_id == first.snapshot.snapshot_id


def test_atrium_code_journey_rejects_repository_change_during_late_source_read(tmp_path: Path, monkeypatch) -> None:
    import core.engine.api.code_intelligence as code_api
    from core.engine.code_intelligence.journey import CodeIntelligenceJourney
    from core.engine.core.config import settings

    root = _repository(tmp_path)
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(root))
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(tmp_path / "index-store"))
    request = code_api.CodeIntelligenceJourneyRequest(
        query="What breaks if used changes?",
        target_path="pkg/service.py",
    )
    first = code_api._prepare_code_journey(request)
    original = CodeIntelligenceJourney._read
    mutated = False

    def _read_then_mutate(journey, path):
        nonlocal mutated
        body = original(journey, path)
        if path == "pkg/service.py" and not mutated:
            mutated = True
            (root / path).write_text(
                "def used() -> int:\n    return 2\n",
                encoding="utf-8",
            )
        return body

    monkeypatch.setattr(CodeIntelligenceJourney, "_read", _read_then_mutate)
    with pytest.raises(ValueError, match="changed while the bounded Code journey was being composed"):
        code_api._prepare_code_journey(
            code_api.CodeIntelligenceJourneyRequest(
                query="What breaks if used changes?",
                target_path="pkg/service.py",
                expected_snapshot_id=first.snapshot.snapshot_id,
                expected_snapshot_digest=first.snapshot.snapshot_digest,
                expected_snapshot_generation=first.snapshot.generation,
            )
        )

    snapshots = code_api._store_for(root).list_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_id == first.snapshot.snapshot_id


def test_atrium_code_journey_rejects_repository_change_during_fresh_scan(tmp_path: Path, monkeypatch) -> None:
    import core.engine.api.code_intelligence as code_api
    from core.engine.code_intelligence.snapshot_store import Phase1IndexIdentityMismatch
    from core.engine.core.config import settings
    from core.engine.intelligence.graph_builder import GraphBuilder

    root = _repository(tmp_path)
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(root))
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(tmp_path / "index-store"))
    original = GraphBuilder.phase1_treesitter

    def _scan_then_mutate(builder):
        result = original(builder)
        (root / "pkg" / "service.py").write_text(
            "def used() -> int:\n    return 2\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(GraphBuilder, "phase1_treesitter", _scan_then_mutate)
    with pytest.raises(Phase1IndexIdentityMismatch, match="changed while the phase-one index was being scanned"):
        code_api._prepare_code_journey(
            code_api.CodeIntelligenceJourneyRequest(
                query="What breaks if used changes?",
                target_path="pkg/service.py",
            )
        )


@pytest.mark.asyncio
async def test_atrium_code_lens_admission_is_explicit_exact_and_body_free(tmp_path: Path, monkeypatch) -> None:
    authority = _AdmissionAuthority()

    response, records, _index_store = await _admission_request(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claims=_admission_claims(),
        authority=authority,
        auth_transport="header",
    )

    assert response.status_code == 200
    body = response.json()
    revision = body["revision"]
    assert body["contract"] == "ace.code-intelligence.atrium-code-lens-admission-response/v1alpha1"
    assert body["source_body_count"] == 0
    assert body["context_bodies_exposed"] is False
    assert body["local_cache_may_write"] is True
    assert body["replayed"] is False
    assert body["transaction_receipt_id"]
    assert body["transaction_receipt_digest"]
    assert revision["product_id"] == ADMISSION_PRODUCT
    assert revision["repository_ref"] == "repository:configured-code-admission"
    assert revision["source_body_count"] == 0
    assert revision["context_bodies_exposed"] is False
    assert revision["local_snapshot_is_product_truth"] is False
    assert revision["source_authority"] is False
    assert revision["reasoning_authority"] is False
    assert revision["delivery_authority"] is False
    assert revision["effect_authority"] is False
    assert '"body"' not in json.dumps(body, sort_keys=True)

    assert len(authority.calls) == 1
    call = authority.calls[0]
    assert call["context"].actor_ref == ADMISSION_ACTOR
    assert call["context"].product_id == ADMISSION_PRODUCT
    assert call["operation"] == "admit_atrium_code_lens_revision"
    assert call["authority"] == "mutate_internal"
    assert call["grant_ref"] == ADMISSION_GRANT
    assert call["use_subject_ref"] == revision["admission_intent_id"]
    assert call["use_subject_digest"] == revision["admission_intent_digest"]

    persisted = tuple(records.records.values())
    assert {item.record_kind for item in persisted} == {
        "task_authentication",
        "atrium_code_lens_revision",
    }
    persisted_json = json.dumps([item.model_dump(mode="json") for item in persisted], sort_keys=True)
    assert '"body"' not in persisted_json
    assert "def used" not in persisted_json


@pytest.mark.asyncio
async def test_atrium_code_lens_admission_rejects_valid_query_token(tmp_path: Path, monkeypatch) -> None:
    authority = _AdmissionAuthority()

    response, records, index_store = await _admission_request(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claims=_admission_claims(),
        authority=authority,
        auth_transport="query",
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert records.records == {}
    assert authority.calls == []
    assert not index_store.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claims", "body_mutation", "expected_status"),
    [
        (None, None, 401),
        (_admission_claims(authorities=[]), None, 403),
        (
            {
                **_admission_claims(),
                "exp": (datetime.now(UTC) - timedelta(minutes=1)).timestamp(),
            },
            None,
            401,
        ),
        (_admission_claims(), "remove_grant", 422),
        (_admission_claims(), "invalid_grant", 422),
    ],
)
async def test_atrium_code_lens_admission_fails_closed_before_local_inspection(
    tmp_path: Path,
    monkeypatch,
    claims: dict | None,
    body_mutation: str | None,
    expected_status: int,
) -> None:
    authority = _AdmissionAuthority()
    request_body = _admission_body()
    if body_mutation == "remove_grant":
        request_body.pop("authority_grant_ref")
    elif body_mutation == "invalid_grant":
        request_body["authority_grant_ref"] = "not a stable grant"

    response, records, index_store = await _admission_request(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claims=claims,
        authority=authority,
        body=request_body,
    )

    assert response.status_code == expected_status
    assert records.records == {}
    assert authority.calls == []
    assert not index_store.exists()


@pytest.mark.asyncio
async def test_atrium_code_lens_admission_denies_inactive_current_grant(tmp_path: Path, monkeypatch) -> None:
    authority = _AdmissionAuthority(deny=True)

    response, records, index_store = await _admission_request(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claims=_admission_claims(),
        authority=authority,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Code-lens admission denied"}
    assert len(authority.calls) == 1
    assert authority.calls[0]["operation"] == "admit_atrium_code_lens_revision"
    assert authority.calls[0]["authority"] == "mutate_internal"
    assert authority.calls[0]["grant_ref"] == ADMISSION_GRANT
    assert {item.record_kind for item in records.records.values()} == {"task_authentication"}
    assert index_store.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_ref", ["", "not a stable repository ref", " repository:must-not-trim"])
async def test_atrium_code_lens_admission_requires_configured_repository_coordinate(
    tmp_path: Path,
    monkeypatch,
    repository_ref: str,
) -> None:
    authority = _AdmissionAuthority()

    response, records, index_store = await _admission_request(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claims=_admission_claims(),
        authority=authority,
        repository_ref=repository_ref,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Code Intelligence repository admission is not configured."}
    assert records.records == {}
    assert authority.calls == []
    assert not index_store.exists()


@pytest.mark.asyncio
async def test_atrium_code_lens_admission_replays_existing_local_snapshot_exactly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    authority = _AdmissionAuthority()

    responses, records, _index_store = await _admission_request(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claims=_admission_claims(),
        authority=authority,
        prewarm_journey=True,
        repetitions=2,
    )

    first, replay = responses
    assert first.status_code == 200
    assert replay.status_code == 200
    first_body = first.json()
    replay_body = replay.json()
    assert first_body["replayed"] is False
    assert replay_body["replayed"] is True
    assert replay_body["revision"] == first_body["revision"]
    assert replay_body["transaction_receipt_id"] == first_body["transaction_receipt_id"]
    assert replay_body["transaction_receipt_digest"] == first_body["transaction_receipt_digest"]
    assert len(authority.calls) == 2
    assert all(call["operation"] == "admit_atrium_code_lens_revision" for call in authority.calls)
    lens_records = [item for item in records.records.values() if item.record_kind == "atrium_code_lens_revision"]
    assert len(lens_records) == 1


@pytest.mark.asyncio
async def test_atrium_code_lens_admission_reports_unavailable_durable_store(tmp_path: Path, monkeypatch) -> None:
    authority = _AdmissionAuthority()
    records = _admission_store(fail_after_records=1)

    response, records, index_store = await _admission_request(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claims=_admission_claims(),
        authority=authority,
        records=records,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Code-lens admission persistence is unavailable."}
    assert records.records == {}
    assert authority.calls == []
    assert index_store.exists()


# ---------------------------------------------------------------------------
# External local-cache snapshot precondition
#
# The cache directory is writable and never self-authenticating: anything with
# write access can rewrite its phase-one state and recompute a fully coherent
# chain, latest pointer, and every derived id and digest.  Reuse therefore
# requires the exact coordinate triple the caller recorded outside it.  These
# coordinates are local reconstruction evidence only, never product truth.
# ---------------------------------------------------------------------------


def _journey_app(tmp_path: Path, monkeypatch, *, index_store: Path | None = None) -> tuple[object, Path, Path]:
    from fastapi import FastAPI

    from core.engine.api.code_intelligence import router
    from core.engine.core.auth import get_header_current_user
    from core.engine.core.config import settings

    root = _repository(tmp_path)
    store_root = index_store if index_store is not None else tmp_path / "index-store"
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(root))
    monkeypatch.setattr(settings, "code_intelligence_product_ref", "product:test")
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(store_root))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_header_current_user] = lambda: {"sub": "user:test", "product": "product:test"}
    return app, root, store_root


async def _journey(app, **extra):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        return await client.post(
            "/v1/code-intelligence/journey",
            json={"query": "What breaks if used changes?", "target_path": "pkg/service.py", **extra},
        )


def _chain(root: Path):
    import core.engine.api.code_intelligence as code_api

    return code_api._store_for(root).list_snapshots()


@pytest.mark.asyncio
async def test_empty_cache_rejects_a_supplied_snapshot_precondition(tmp_path: Path, monkeypatch) -> None:
    app, root, store_root = _journey_app(tmp_path, monkeypatch)

    response = await _journey(
        app,
        expected_snapshot_id="code_index_snapshot:" + "a" * 32,
        expected_snapshot_digest="sha256:" + "b" * 64,
        expected_snapshot_generation=1,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Code Intelligence local index snapshot precondition was not satisfied."}
    assert not any(store_root.rglob("snapshot-*.json"))


@pytest.mark.asyncio
async def test_nonempty_cache_rejects_a_missing_snapshot_precondition(tmp_path: Path, monkeypatch) -> None:
    app, root, _store_root = _journey_app(tmp_path, monkeypatch)
    first = await _journey(app)
    assert first.status_code == 200

    response = await _journey(app)

    assert response.status_code == 409
    assert response.json() == {"detail": "Code Intelligence local index snapshot precondition was not satisfied."}
    chain = _chain(root)
    assert len(chain) == 1
    assert chain[0].snapshot_id == first.json()["index_snapshot_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "omitted",
    ["expected_snapshot_id", "expected_snapshot_digest", "expected_snapshot_generation"],
)
async def test_partial_snapshot_precondition_is_rejected_as_malformed(
    tmp_path: Path,
    monkeypatch,
    omitted: str,
) -> None:
    app, root, _store_root = _journey_app(tmp_path, monkeypatch)
    first = await _journey(app)
    assert first.status_code == 200
    supplied = _precondition(first.json())
    supplied.pop(omitted)

    response = await _journey(app, **supplied)

    assert response.status_code == 422
    assert "must be supplied together" in json.dumps(response.json())
    assert len(_chain(root)) == 1


@pytest.mark.asyncio
async def test_unchanged_repository_reopens_only_with_the_externally_supplied_pair(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, root, _store_root = _journey_app(tmp_path, monkeypatch)
    first = (await _journey(app)).json()

    reopened = await _journey(app, **_precondition(first))

    assert reopened.status_code == 200
    body = reopened.json()
    assert body["index_reopened"] is True
    assert body["index_generation"] == 1
    assert body["index_snapshot_id"] == first["index_snapshot_id"]
    assert body["index_snapshot_digest"] == first["index_snapshot_digest"]
    assert len(_chain(root)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("crossed", ["id", "digest", "generation"])
async def test_crossed_or_forged_snapshot_coordinates_fail_closed(
    tmp_path: Path,
    monkeypatch,
    crossed: str,
) -> None:
    app, root, _store_root = _journey_app(tmp_path, monkeypatch)
    first = (await _journey(app)).json()
    supplied = _precondition(first)
    if crossed == "id":
        supplied["expected_snapshot_id"] = "code_index_snapshot:" + "c" * 32
    elif crossed == "digest":
        supplied["expected_snapshot_digest"] = "sha256:" + "d" * 64
    else:
        supplied["expected_snapshot_generation"] = 2

    response = await _journey(app, **supplied)

    assert response.status_code == 409
    chain = _chain(root)
    assert len(chain) == 1
    assert chain[0].snapshot_id == first["index_snapshot_id"]


@pytest.mark.asyncio
async def test_changed_repository_captures_a_child_bound_to_the_exact_supplied_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, root, _store_root = _journey_app(tmp_path, monkeypatch)
    first = (await _journey(app)).json()
    (root / "pkg" / "service.py").write_text(
        "def used() -> int:\n    return 1\n\ndef newly_observed() -> int:\n    return 2\n",
        encoding="utf-8",
    )

    updated = await _journey(app, **_precondition(first))

    assert updated.status_code == 200
    body = updated.json()
    assert body["index_reopened"] is False
    assert body["index_generation"] == 2
    chain = _chain(root)
    assert len(chain) == 2
    assert chain[1].parent_snapshot_id == first["index_snapshot_id"]
    assert chain[1].parent_snapshot_digest == first["index_snapshot_digest"]
    assert chain[1].snapshot_digest == body["index_snapshot_digest"]


@pytest.mark.asyncio
async def test_stale_snapshot_precondition_cannot_append_a_second_child(tmp_path: Path, monkeypatch) -> None:
    app, root, _store_root = _journey_app(tmp_path, monkeypatch)
    first = (await _journey(app)).json()
    (root / "pkg" / "service.py").write_text(
        "def used() -> int:\n    return 1\n\ndef newly_observed() -> int:\n    return 2\n",
        encoding="utf-8",
    )
    second = await _journey(app, **_precondition(first))
    assert second.status_code == 200
    (root / "pkg" / "service.py").write_text(
        "def used() -> int:\n    return 1\n\ndef third_state() -> int:\n    return 3\n",
        encoding="utf-8",
    )

    # A concurrent caller still holding the first generation loses the race
    # rather than silently renumbering onto the winner's chain.
    stale = await _journey(app, **_precondition(first))

    assert stale.status_code == 409
    assert stale.json() == {"detail": "Code Intelligence local index generation changed concurrently."}
    assert len(_chain(root)) == 2


@pytest.mark.asyncio
async def test_admission_inherits_the_same_external_precondition_contract(tmp_path: Path, monkeypatch) -> None:
    authority = _AdmissionAuthority()

    response, records, _index_store = await _admission_request(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claims=_admission_claims(),
        authority=authority,
        body={**_admission_body(), "expected_snapshot_generation": 1},
    )

    assert response.status_code == 422
    assert "must be supplied together" in json.dumps(response.json())
    assert records.records == {}
    assert authority.calls == []


@pytest.mark.asyncio
async def test_admission_against_a_warm_cache_requires_the_external_precondition(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from fastapi import FastAPI

    from core.engine.api.code_intelligence import router
    from core.engine.code_intelligence.resource_plane import (
        AtriumCodeLensAdmissionHttpRuntime,
        atrium_code_lens_admission_runtime,
    )
    from core.engine.core.auth import get_current_user, get_header_current_user
    from core.engine.core.config import settings

    root = _repository(tmp_path)
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(root))
    monkeypatch.setattr(settings, "code_intelligence_product_ref", ADMISSION_PRODUCT)
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(tmp_path / "index-store"))
    monkeypatch.setattr(settings, "code_intelligence_repository_ref", "repository:configured-code-admission")
    claims = _admission_claims()
    authority = _AdmissionAuthority()
    records = _admission_store()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[get_header_current_user] = lambda: claims
    app.dependency_overrides[atrium_code_lens_admission_runtime] = lambda: AtriumCodeLensAdmissionHttpRuntime(
        records=records,
        authority=authority,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        warm = await client.post(
            "/v1/code-intelligence/journey",
            json={"query": "What breaks if used changes?", "target_path": "pkg/service.py"},
        )
        assert warm.status_code == 200
        response = await client.post("/v1/code-intelligence/admissions", json=_admission_body())

    assert response.status_code == 409
    assert response.json() == {"detail": "Code Intelligence local index snapshot precondition was not satisfied."}
    assert {item.record_kind for item in records.records.values()} <= {"task_authentication"}
    assert authority.calls == []


# ---------------------------------------------------------------------------
# Governed admission product fence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_product", "principal_product", "expected_status", "expected_detail"),
    [
        ("", ADMISSION_PRODUCT, 503, "Code Intelligence product inspection is not configured."),
        (" product:untrimmed", ADMISSION_PRODUCT, 503, "Code Intelligence product inspection is not configured."),
        (ADMISSION_PRODUCT, None, 401, "Verified token lacks product scope"),
        (ADMISSION_PRODUCT, "", 401, "Verified token lacks product scope"),
        (
            ADMISSION_PRODUCT,
            "product:other",
            403,
            "Code Intelligence repository inspection is not available for this product.",
        ),
    ],
)
async def test_admission_fences_the_configured_product_before_repository_or_cache_access(
    tmp_path: Path,
    monkeypatch,
    configured_product: str,
    principal_product: str | None,
    expected_status: int,
    expected_detail: str,
) -> None:
    from fastapi import FastAPI

    import core.engine.api.code_intelligence as code_api
    from core.engine.code_intelligence.resource_plane import (
        AtriumCodeLensAdmissionHttpRuntime,
        atrium_code_lens_admission_runtime,
    )
    from core.engine.core.auth import get_current_user, get_header_current_user
    from core.engine.core.config import settings

    repository = _repository(tmp_path)
    index_store = tmp_path / "index-store"
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(repository))
    monkeypatch.setattr(settings, "code_intelligence_product_ref", configured_product)
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", str(index_store))
    monkeypatch.setattr(settings, "code_intelligence_repository_ref", "repository:configured-code-admission")
    accessed: list[str] = []

    def _unexpected_journey(*_args, **_kwargs):
        accessed.append("repository")
        raise AssertionError("repository inspection must not start")

    def _unexpected_store(*_args, **_kwargs):
        accessed.append("cache")
        raise AssertionError("local cache must not initialize")

    monkeypatch.setattr(code_api, "CodeIntelligenceJourney", _unexpected_journey)
    monkeypatch.setattr(code_api, "_store_for", _unexpected_store)
    claims = dict(_admission_claims())
    if principal_product is None:
        claims.pop("product")
    else:
        claims["product"] = principal_product
    authority = _AdmissionAuthority()
    records = _admission_store()
    app = FastAPI()
    app.include_router(code_api.router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[get_header_current_user] = lambda: claims
    app.dependency_overrides[atrium_code_lens_admission_runtime] = lambda: AtriumCodeLensAdmissionHttpRuntime(
        records=records,
        authority=authority,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.post("/v1/code-intelligence/admissions", json=_admission_body())

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    if expected_status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    assert accessed == []
    assert records.records == {}
    assert authority.calls == []
    assert not index_store.exists()


# ---------------------------------------------------------------------------
# Local index cache-root containment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store_root_spelling",
    [
        "",
        "   ",
        " /tmp/untrimmed",
        "relative/cache",
        "repository",
        "repository/cache",
        "repository/../repo/cache",
        "symlink_to_repository",
        "symlink_into_repository",
    ],
)
async def test_journey_rejects_an_index_cache_root_inside_the_repository(
    tmp_path: Path,
    monkeypatch,
    store_root_spelling: str,
) -> None:
    from fastapi import FastAPI

    import core.engine.api.code_intelligence as code_api
    from core.engine.core.auth import get_header_current_user
    from core.engine.core.config import settings

    repository = _repository(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    if store_root_spelling == "symlink_to_repository":
        (outside / "link").symlink_to(repository, target_is_directory=True)
        store_root = str(outside / "link")
    elif store_root_spelling == "symlink_into_repository":
        (outside / "inner").symlink_to(repository / "pkg", target_is_directory=True)
        store_root = str(outside / "inner")
    elif store_root_spelling.startswith("repository"):
        store_root = str(repository) + store_root_spelling.removeprefix("repository")
    else:
        store_root = store_root_spelling
    monkeypatch.setattr(settings, "code_intelligence_repository_root", str(repository))
    monkeypatch.setattr(settings, "code_intelligence_product_ref", "product:test")
    monkeypatch.setattr(settings, "code_intelligence_index_store_root", store_root)
    opened: list[str] = []
    monkeypatch.setattr(
        code_api,
        "CodeIntelligenceJourney",
        lambda *_args, **_kwargs: opened.append("repository"),
    )
    app = FastAPI()
    app.include_router(code_api.router)
    app.dependency_overrides[get_header_current_user] = lambda: {"sub": "user:test", "product": "product:test"}

    response = await _journey(app)

    assert response.status_code == 503
    assert response.json() == {"detail": "Code Intelligence repository inspection is not configured."}
    assert opened == []
    assert not any(repository.rglob("snapshot-*.json"))
    assert not (repository / ".snapshot-store.lock").exists()


def test_settings_reject_an_index_cache_root_inside_the_repository(tmp_path: Path) -> None:
    from pydantic import ValidationError

    from core.engine.core.config import Settings

    repository = tmp_path / "repo"
    repository.mkdir()
    outside = tmp_path / "cache"

    accepted = Settings(
        jwt_secret="unit-test-secret",
        code_intelligence_repository_root=str(repository),
        code_intelligence_index_store_root=str(outside),
    )
    assert accepted.code_intelligence_index_store_root == str(outside)

    for spelling in (str(repository), str(repository / "cache"), f"{repository}/../repo/cache"):
        with pytest.raises(ValidationError, match="must be outside"):
            Settings(
                jwt_secret="unit-test-secret",
                code_intelligence_repository_root=str(repository),
                code_intelligence_index_store_root=spelling,
            )


def test_settings_reject_a_symlinked_index_cache_root_inside_the_repository(tmp_path: Path) -> None:
    from pydantic import ValidationError

    from core.engine.core.config import Settings

    repository = tmp_path / "repo"
    (repository / "pkg").mkdir(parents=True)
    link = tmp_path / "aliased-cache"
    link.symlink_to(repository / "pkg", target_is_directory=True)

    with pytest.raises(ValidationError, match="must be outside"):
        Settings(
            jwt_secret="unit-test-secret",
            code_intelligence_repository_root=str(repository),
            code_intelligence_index_store_root=str(link),
        )
