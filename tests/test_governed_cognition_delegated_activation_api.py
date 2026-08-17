"""Slice 7 delegated-activation API boundary and human-route hardening.

The human/local-owner review path stays the interactive default and keeps its
exact behaviour. A service token can never reach it, a human token can never
reach the delegated path, and neither path adds a public MCP tool.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import core.engine.api.cognition as cognition_api
from core.engine.core.auth import (
    create_access_token,
    get_current_user,
    get_header_current_user,
    is_human_principal,
    service_principal_ref,
    verify_token,
)
from core.engine.core.config import settings
from tests.delegated_cognition_support import (
    PRODUCT,
    SERVICE_ACTOR,
    build_proposal,
    build_request,
    model_participant,
    principal_binding,
    service_principal,
)

HUMAN_CLAIMS = {"sub": "user:default", "product": PRODUCT, "authorities": ["cognition-review"], "local_owner": True}
API_AUTHENTICATED_AT = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1)
API_AUTHENTICATION_EXPIRES_AT = API_AUTHENTICATED_AT + timedelta(minutes=30)


class _RefusingPool:
    """Any repository access at all is a boundary failure for these cases."""

    def __init__(self) -> None:
        self.opened = 0

    @asynccontextmanager
    async def connection(self):
        self.opened += 1
        raise AssertionError("delegated boundary reached storage before validating product and principal")
        yield  # pragma: no cover


@pytest.fixture
async def client():
    app = FastAPI()
    app.include_router(cognition_api.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value, app


def _service_claims(principal_ref: str) -> dict:
    return {
        "sub": SERVICE_ACTOR,
        "product": PRODUCT,
        "authorities": [],
        "principal_kind": "service",
        "agent_principal": principal_ref,
        "iat": int(API_AUTHENTICATED_AT.timestamp()),
        "exp": int(API_AUTHENTICATION_EXPIRES_AT.timestamp()),
    }


def _body(**overrides):
    principal = service_principal()
    proposal = build_proposal()
    request = build_request(
        proposal,
        principal,
        authenticated_at=API_AUTHENTICATED_AT,
        expires_at=API_AUTHENTICATION_EXPIRES_AT,
    )
    payload = {
        "request": request.model_dump(mode="json"),
        "principal": principal.model_dump(mode="json"),
    }
    payload.update(overrides)
    return payload, request, principal


# --------------------------------------------------------------------------
# Token claim hardening.
# --------------------------------------------------------------------------


def test_absent_principal_kind_claim_stays_the_human_default() -> None:
    assert is_human_principal({"sub": "user:default"}) is True
    assert service_principal_ref({"sub": "user:default"}) is None
    assert is_human_principal({"sub": "user:default", "principal_kind": "human"}) is True


@pytest.mark.parametrize(
    "subject", ["service:worker", "system:planner", "model:worker", "agent:worker", "external:worker"]
)
def test_reserved_machine_subject_without_signed_kind_is_rejected(subject: str) -> None:
    token = create_access_token({"sub": subject, "product": PRODUCT, "authorities": []})
    with pytest.raises(Exception) as invalid:
        verify_token(token)
    assert invalid.value.status_code == 401


@pytest.mark.parametrize(
    "subject",
    [
        "service:worker",
        "system:planner",
        "model:worker",
        "model-agent:worker",
        "agent:worker",
        "external:worker",
    ],
)
def test_signed_human_kind_cannot_reclassify_a_reserved_machine_subject(subject: str) -> None:
    token = create_access_token(
        {
            "sub": subject,
            "product": PRODUCT,
            "authorities": ["cognition-review"],
            "local_owner": True,
            "principal_kind": "human",
        }
    )

    with pytest.raises(Exception) as invalid:
        verify_token(token)

    assert invalid.value.status_code == 401
    assert is_human_principal({"sub": subject, "principal_kind": "human", "local_owner": True}) is False


@pytest.mark.parametrize("kind", ["model_agent", "external_agent"])
def test_explicit_non_service_machine_kind_is_never_human(kind: str) -> None:
    claims = {"sub": f"agent:{kind}", "principal_kind": kind, "agent_principal": f"agent_principal:{kind}"}
    assert is_human_principal(claims) is False
    assert service_principal_ref(claims) is None


def test_service_token_is_never_also_the_local_owner() -> None:
    token = create_access_token(
        {
            "sub": SERVICE_ACTOR,
            "product": PRODUCT,
            "authorities": [],
            "local_owner": True,
            "principal_kind": "service",
            "agent_principal": "agent_principal:x",
        }
    )
    with pytest.raises(Exception) as invalid:
        verify_token(token)
    assert invalid.value.status_code == 401


def test_service_token_must_name_its_exact_principal() -> None:
    token = create_access_token(
        {"sub": SERVICE_ACTOR, "product": PRODUCT, "authorities": [], "principal_kind": "service"}
    )
    with pytest.raises(Exception) as invalid:
        verify_token(token)
    assert invalid.value.status_code == 401


def test_unknown_principal_kind_is_rejected() -> None:
    token = create_access_token(
        {"sub": SERVICE_ACTOR, "product": PRODUCT, "principal_kind": "superuser", "agent_principal": "a:b"}
    )
    with pytest.raises(Exception) as invalid:
        verify_token(token)
    assert invalid.value.status_code == 401


def test_local_owner_token_round_trips_unchanged() -> None:
    token = create_access_token(HUMAN_CLAIMS)
    claims = verify_token(token)
    assert claims["local_owner"] is True
    assert "principal_kind" not in claims
    assert is_human_principal(claims) is True


def test_legacy_human_token_without_iat_remains_compatible() -> None:
    payload = dict(HUMAN_CLAIMS)
    payload["exp"] = datetime.now(UTC) + timedelta(minutes=5)
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    claims = verify_token(token)

    assert "iat" not in claims
    assert is_human_principal(claims) is True


def test_bounded_generic_legacy_subject_validates_without_becoming_human() -> None:
    token = create_access_token(
        {
            "sub": "principal:code-operator",
            "product": "product:code-admission",
            "authorities": ["mutate_internal"],
        }
    )

    claims = verify_token(token)

    assert claims["sub"] == "principal:code-operator"
    assert is_human_principal(claims) is False
    assert service_principal_ref(claims) is None


async def test_generic_legacy_subject_cannot_review_or_teach_human_cognition_before_storage(
    client, monkeypatch
) -> None:
    http, app = client
    claims = {
        "sub": "principal:code-operator",
        "product": PRODUCT,
        "authorities": ["cognition-review"],
    }
    app.dependency_overrides[get_current_user] = lambda: claims
    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)

    review = await http.post(
        "/cognition/proposals/proposal:x/review",
        json={
            "review_request_id": "review-request:x",
            "disposition": "approve",
            "rationale": "generic principal must not become human",
            "expected_head_generation": 0,
        },
    )
    teach = await http.post(
        "/cognition/proposals/from-task",
        json={
            "task_id": "task:source",
            "stable_key": "generic_principal_attempt",
            "name": "Generic principal attempt",
            "description": "This must stop before repository access.",
            "intent": "Prove compatibility does not widen human authority.",
        },
    )

    assert review.status_code == 403
    assert teach.status_code == 403
    assert review.json()["detail"] == {"code": "human_authority_required"}
    assert teach.json()["detail"] == {"code": "human_authority_required"}
    assert refusing.opened == 0


# --------------------------------------------------------------------------
# The human/legacy route never accepts a service token.
# --------------------------------------------------------------------------


async def test_human_review_route_denies_a_service_token_carrying_the_authority_string(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    claims = _service_claims(str(principal.principal_id))
    # Even if a service token were minted with the human authority string, the
    # canonical human route must not coerce it into HUMAN.
    claims["authorities"] = ["cognition-review"]
    app.dependency_overrides[get_current_user] = lambda: claims
    pool = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", pool)

    response = await http.post(
        "/cognition/proposals/proposal:x/review",
        json={
            "review_request_id": "review-request:x",
            "disposition": "approve",
            "rationale": "attempted service coercion",
            "expected_head_generation": 0,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "human_authority_required"}
    assert pool.opened == 0


async def test_lifecycle_route_denies_a_service_token(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_current_user] = lambda: _service_claims(str(principal.principal_id))
    pool = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", pool)

    response = await http.post(
        "/cognition/heads/cognition_head:x/lifecycle",
        json={
            "review_request_id": "review-request:x",
            "action": "rollback",
            "rationale": "attempted delegated lifecycle",
            "expected_head_generation": 1,
            "target_revision_id": "cognition_revision:y",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "human_authority_required"}
    assert pool.opened == 0


async def test_teach_route_denies_a_service_token(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_current_user] = lambda: _service_claims(str(principal.principal_id))

    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)
    response = await http.post(
        "/cognition/proposals/from-task",
        json={
            "task_id": "task:source",
            "stable_key": "taught_recipe",
            "name": "Taught Recipe",
            "description": "A recipe taught from an accepted task.",
            "intent": "Reuse the accepted framing sequence.",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "human_authority_required"}
    assert refusing.opened == 0


# --------------------------------------------------------------------------
# The delegated route never accepts a human token and is header-only.
# --------------------------------------------------------------------------


async def test_delegated_route_requires_authentication(client) -> None:
    http, _ = client
    payload, _, _ = _body()
    response = await http.post("/cognition/delegated/activations", json=payload)
    assert response.status_code == 401


async def test_delegated_mutation_is_header_only(client) -> None:
    http, _ = client
    payload, _, _ = _body()
    token = create_access_token(_service_claims("agent_principal:x"))
    response = await http.post(f"/cognition/delegated/reviews?token={token}", json=payload)
    assert response.status_code == 401


@pytest.mark.parametrize("route", ["/cognition/delegated/reviews", "/cognition/delegated/activations"])
async def test_delegated_route_routes_a_human_token_back_to_human_review(client, monkeypatch, route) -> None:
    http, app = client
    app.dependency_overrides[get_header_current_user] = lambda: dict(HUMAN_CLAIMS)
    pool = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", pool)
    payload, _, _ = _body()

    response = await http.post(route, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "human_review_required"}
    assert pool.opened == 0


async def test_delegated_route_denies_a_token_for_another_principal(client, monkeypatch) -> None:
    http, app = client
    app.dependency_overrides[get_header_current_user] = lambda: _service_claims("agent_principal:someone-else")
    pool = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", pool)
    payload, _, _ = _body()

    response = await http.post("/cognition/delegated/reviews", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "delegated_request_mismatch"}
    assert pool.opened == 0


async def test_delegated_route_denies_a_cross_product_envelope(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    claims = _service_claims(str(principal.principal_id))
    claims["product"] = "product:beta"
    app.dependency_overrides[get_header_current_user] = lambda: claims
    pool = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", pool)
    payload, _, _ = _body()

    response = await http.post("/cognition/delegated/activations", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "delegated_request_mismatch"}
    assert pool.opened == 0


async def test_delegated_route_denies_an_altered_envelope(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_header_current_user] = lambda: _service_claims(str(principal.principal_id))
    pool = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", pool)
    payload, _, _ = _body()
    payload["request"]["expected_head_generation"] = 7

    response = await http.post("/cognition/delegated/reviews", json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert pool.opened == 0


async def test_delegated_route_requires_supplied_content_identities(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_header_current_user] = lambda: _service_claims(str(principal.principal_id))
    pool = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", pool)
    payload, _, _ = _body()
    payload["request"].pop("request_digest")

    response = await http.post("/cognition/delegated/activations", json=payload)

    assert response.status_code == 422
    assert pool.opened == 0


async def test_delegated_route_forbids_extra_body_fields(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_header_current_user] = lambda: _service_claims(str(principal.principal_id))
    monkeypatch.setattr(cognition_api, "pool", _RefusingPool())
    payload, _, _ = _body()
    payload["escalate"] = True

    response = await http.post("/cognition/delegated/reviews", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iat", None),
        ("iat", True),
        ("iat", "1700000000"),
        ("iat", 1.5),
        ("iat", float("nan")),
        ("iat", float("inf")),
        ("exp", None),
        ("exp", False),
        ("exp", "2700000000"),
        ("exp", 1.5),
        ("exp", float("nan")),
        ("exp", float("inf")),
    ],
)
async def test_delegated_route_rejects_invalid_signed_numeric_dates_before_storage(
    client, monkeypatch, claim: str, value: object
) -> None:
    http, app = client
    principal = service_principal()
    claims = _service_claims(str(principal.principal_id))
    if value is None:
        claims.pop(claim)
    else:
        claims[claim] = value
    app.dependency_overrides[get_header_current_user] = lambda: claims
    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)
    payload, _, _ = _body()

    response = await http.post("/cognition/delegated/reviews", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"
    assert refusing.opened == 0


@pytest.mark.parametrize("window", ["expired", "future", "reversed"])
async def test_delegated_route_rejects_invalid_signed_windows_before_storage(client, monkeypatch, window) -> None:
    http, app = client
    principal = service_principal()
    claims = _service_claims(str(principal.principal_id))
    now = int(datetime.now(UTC).timestamp())
    if window == "expired":
        claims.update(iat=now - 120, exp=now - 1)
    elif window == "future":
        claims.update(iat=now + 120, exp=now + 240)
    else:
        claims.update(iat=now + 30, exp=now + 20)
    app.dependency_overrides[get_header_current_user] = lambda: claims
    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)
    payload, _, _ = _body()

    response = await http.post("/cognition/delegated/activations", json=payload)

    assert response.status_code == 401
    assert refusing.opened == 0


async def test_caller_supplied_authentication_coordinates_must_equal_signed_claims(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_header_current_user] = lambda: _service_claims(str(principal.principal_id))
    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)
    proposal = build_proposal()
    forged = build_request(
        proposal,
        principal,
        authenticated_at=API_AUTHENTICATED_AT - timedelta(minutes=5),
        expires_at=API_AUTHENTICATION_EXPIRES_AT,
    )

    response = await http.post(
        "/cognition/delegated/reviews",
        json={"request": forged.model_dump(mode="json"), "principal": principal.model_dump(mode="json")},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {"code": "delegated_request_mismatch"}
    assert refusing.opened == 0


async def test_unverifiable_model_participant_is_rejected_before_storage(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_header_current_user] = lambda: _service_claims(str(principal.principal_id))
    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)
    request = build_request(
        build_proposal(),
        principal,
        participant=model_participant(),
        authenticated_at=API_AUTHENTICATED_AT,
        expires_at=API_AUTHENTICATION_EXPIRES_AT,
    )

    response = await http.post(
        "/cognition/delegated/reviews",
        json={"request": request.model_dump(mode="json"), "principal": principal.model_dump(mode="json")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "delegated_participant_unverifiable"}
    assert refusing.opened == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["principal"].update({"unexpected": "value"}),
        lambda payload: payload["principal"].update({"lifecycle_revision": "1"}),
        lambda payload: payload["request"].update({"expected_head_generation": "0"}),
        lambda payload: payload["request"]["service_principal"].update({"unexpected": "value"}),
    ],
)
async def test_nested_delegated_models_forbid_extras_and_lax_coercion(client, monkeypatch, mutate) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_header_current_user] = lambda: _service_claims(str(principal.principal_id))
    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)
    payload, _, _ = _body()
    mutate(payload)

    response = await http.post("/cognition/delegated/reviews", json=payload)

    assert response.status_code == 422
    assert refusing.opened == 0


@pytest.mark.parametrize(
    "size", [cognition_api.MAX_DELEGATED_REQUEST_BODY_BYTES, cognition_api.MAX_DELEGATED_REQUEST_BODY_BYTES + 1]
)
async def test_delegated_body_limit_is_enforced_before_parsing_and_storage(client, monkeypatch, size: int) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_header_current_user] = lambda: _service_claims(str(principal.principal_id))
    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)
    prefix, suffix = b'{"padding":"', b'"}'
    content = prefix + (b"x" * (size - len(prefix) - len(suffix))) + suffix

    response = await http.post(
        "/cognition/delegated/reviews",
        content=content,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == (413 if size > cognition_api.MAX_DELEGATED_REQUEST_BODY_BYTES else 422)
    if response.status_code == 413:
        assert response.json()["detail"] == {"code": "delegated_request_too_large"}
    assert refusing.opened == 0


async def test_deep_delegated_json_fails_before_storage(client, monkeypatch) -> None:
    http, app = client
    principal = service_principal()
    app.dependency_overrides[get_header_current_user] = lambda: _service_claims(str(principal.principal_id))
    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)
    content = b'{"request":' + b"[" * 300 + b"0" + b"]" * 300 + b',"principal":{}}'

    response = await http.post(
        "/cognition/delegated/reviews",
        content=content,
        headers={"content-type": "application/json"},
    )

    assert response.status_code in {400, 422}
    assert refusing.opened == 0


async def test_delegated_receipt_path_id_is_bounded_before_storage(client, monkeypatch) -> None:
    http, app = client
    app.dependency_overrides[get_current_user] = lambda: dict(HUMAN_CLAIMS)
    refusing = _RefusingPool()
    monkeypatch.setattr(cognition_api, "pool", refusing)

    response = await http.get("/cognition/delegated/approvals/" + "a" * 241)

    assert response.status_code == 422
    assert refusing.opened == 0


# --------------------------------------------------------------------------
# Surface bounds.
# --------------------------------------------------------------------------


def test_delegated_surface_adds_no_lifecycle_or_issuance_route() -> None:
    paths = {route.path for route in cognition_api.router.routes}
    delegated = {path for path in paths if "/delegated/" in path}
    assert delegated == {
        "/cognition/delegated/reviews",
        "/cognition/delegated/activations",
        "/cognition/delegated/approvals/{receipt_id}",
        "/cognition/delegated/activations/{receipt_id}",
    }
    assert not any(token in path for path in delegated for token in ("grant", "issue", "mint", "lifecycle"))
    # The human lifecycle route is unchanged and remains the only lifecycle path.
    assert "/cognition/heads/{head_id}/lifecycle" in paths


async def test_public_mcp_tool_surface_remains_exactly_eleven() -> None:
    from ace_mcp_client.server import mcp

    tools = await mcp.list_tools()
    assert len(tools) == 11


def test_delegated_request_and_principal_bindings_are_content_derived() -> None:
    principal = service_principal()
    binding = principal_binding(principal)
    assert binding.principal_ref == str(principal.principal_id)
    assert binding.registration_ref == binding.principal_ref
    assert binding.registration_digest == binding.principal_digest
