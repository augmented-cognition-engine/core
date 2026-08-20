# engine/core/auth.py
import math
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError

from ace.application.agent_composition_runtime import TaskAuthenticationReceiptV1Alpha1
from core.engine.core.config import require_jwt_secret, settings

_bearer = HTTPBearer(auto_error=False)
_AUTHORITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
MAX_TOKEN_AUTHORITIES = 50

# Optional additive claim. Absent means the historical human/local-owner default,
# so every existing token keeps its exact meaning.
HUMAN_PRINCIPAL_KIND = "human"
SERVICE_PRINCIPAL_KIND = "service"
_PRINCIPAL_KINDS = frozenset({HUMAN_PRINCIPAL_KIND, SERVICE_PRINCIPAL_KIND, "model_agent", "external_agent"})
_LEGACY_HUMAN_SUBJECT_PREFIXES = ("user:", "human:", "local-owner:")
_RESERVED_NON_HUMAN_SUBJECT_PREFIXES = (
    "service:",
    "system:",
    "model:",
    "model-agent:",
    "agent:",
    "external:",
)
DELEGATED_AUTHENTICATION_POLICY = "jwt:ace-api-delegated-service:v1"
DELEGATED_AUTH_CLOCK_SKEW_SECONDS = 60


def _invalid_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _validate_claims(payload: dict) -> dict:
    for claim in ("sub", "product"):
        value = payload.get(claim)
        if value is not None and (not isinstance(value, str) or not value or len(value) > 240):
            raise _invalid_token()
    authorities = payload.get("authorities")
    if authorities is not None and (
        not isinstance(authorities, list)
        or len(authorities) > MAX_TOKEN_AUTHORITIES
        or any(not isinstance(item, str) or not _AUTHORITY.fullmatch(item) for item in authorities)
    ):
        raise _invalid_token()
    if "local_owner" in payload and not isinstance(payload["local_owner"], bool):
        raise _invalid_token()
    principal_kind = payload.get("principal_kind")
    if principal_kind is not None and (not isinstance(principal_kind, str) or principal_kind not in _PRINCIPAL_KINDS):
        raise _invalid_token()
    agent_principal = payload.get("agent_principal")
    if agent_principal is not None and (
        not isinstance(agent_principal, str) or not agent_principal or len(agent_principal) > 240
    ):
        raise _invalid_token()
    subject = payload.get("sub")
    if principal_kind is None:
        # Historical generic subjects remain valid token identities, but only
        # unmistakable human/local subjects pass ``is_human_principal`` below.
        # Reserved machine identities must carry their signed kind.
        if (
            not isinstance(subject, str)
            or agent_principal is not None
            or subject.startswith(_RESERVED_NON_HUMAN_SUBJECT_PREFIXES)
        ):
            raise _invalid_token()
    elif principal_kind == HUMAN_PRINCIPAL_KIND:
        if (
            agent_principal is not None
            or not isinstance(subject, str)
            or subject.startswith(_RESERVED_NON_HUMAN_SUBJECT_PREFIXES)
        ):
            raise _invalid_token()
    # A non-human principal is never also the local owner, and a service token
    # must name the exact registered principal it claims to act for. Trusted
    # human/local-owner proof and delegated service flow stay distinct.
    if principal_kind is not None and principal_kind != HUMAN_PRINCIPAL_KIND:
        if payload.get("local_owner") is True or agent_principal is None:
            raise _invalid_token()
    return payload


def is_human_principal(user: dict) -> bool:
    """Return whether the verified claims describe a human/local-owner caller."""

    kind = user.get("principal_kind")
    if kind is not None:
        subject = user.get("sub")
        return (
            kind == HUMAN_PRINCIPAL_KIND
            and isinstance(subject, str)
            and user.get("agent_principal") is None
            and not subject.startswith(_RESERVED_NON_HUMAN_SUBJECT_PREFIXES)
        )
    subject = user.get("sub")
    return (
        isinstance(subject, str)
        and user.get("agent_principal") is None
        and not subject.startswith(_RESERVED_NON_HUMAN_SUBJECT_PREFIXES)
        and (user.get("local_owner") is True or subject.startswith(_LEGACY_HUMAN_SUBJECT_PREFIXES))
    )


def service_principal_ref(user: dict) -> str | None:
    """Return the exact registered SERVICE principal a token acts for, if any."""

    if str(user.get("principal_kind") or "") != SERVICE_PRINCIPAL_KIND:
        return None
    value = user.get("agent_principal")
    return value if isinstance(value, str) and value else None


def delegated_authentication_receipt(
    claims: dict,
    *,
    evaluated_at: datetime,
) -> TaskAuthenticationReceiptV1Alpha1:
    """Derive controller-owned authentication evidence from signed SERVICE claims.

    The JWT NumericDate claims, not request JSON, own the validity interval.
    No credential-derived material is retained.
    """

    if claims.get("principal_kind") != SERVICE_PRINCIPAL_KIND:
        raise _invalid_token()
    values: dict[str, int] = {}
    for name in ("iat", "exp"):
        raw = claims.get(name)
        if (
            not isinstance(raw, (int, float))
            or isinstance(raw, bool)
            or not math.isfinite(raw)
            or not float(raw).is_integer()
        ):
            raise _invalid_token()
        values[name] = int(raw)
    try:
        authenticated_at = datetime.fromtimestamp(values["iat"], tz=UTC)
        expires_at = datetime.fromtimestamp(values["exp"], tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise _invalid_token() from exc
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("evaluated_at must include a timezone")
    evaluated_at = evaluated_at.astimezone(UTC)
    if (
        authenticated_at >= expires_at
        or expires_at <= evaluated_at
        or authenticated_at > evaluated_at + timedelta(seconds=DELEGATED_AUTH_CLOCK_SKEW_SECONDS)
    ):
        raise _invalid_token()
    actor_ref = claims.get("sub")
    product_id = claims.get("product")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise _invalid_token()
    return TaskAuthenticationReceiptV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        verification_policy_ref=DELEGATED_AUTHENTICATION_POLICY,
        authenticated_at=authenticated_at,
        expires_at=expires_at,
        credential_fingerprint=None,
    )


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    payload = data.copy()
    issued_at = datetime.now(timezone.utc)
    expire = issued_at + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    payload.setdefault("iat", int(issued_at.timestamp()))
    payload["exp"] = expire
    return jwt.encode(payload, require_jwt_secret(), algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict:
    try:
        return _validate_claims(
            jwt.decode(
                token,
                require_jwt_secret(),
                algorithms=[settings.jwt_algorithm],
            )
        )
    except InvalidTokenError:
        raise _invalid_token()


def verify_ownership(record: dict, user: dict) -> None:
    """Verify the requesting user's org matches the record's org. Returns 404 to avoid leaking existence."""
    record_org = str(record.get("product", ""))
    user_org = str(user.get("product", ""))
    if record_org and user_org and record_org != user_org:
        raise HTTPException(status_code=404, detail="Not found")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    # Header auth: Authorization: Bearer <token>
    if credentials:
        return verify_token(credentials.credentials)
    # Query param auth: ?token=<token> — used by EventSource (SSE) which can't set headers
    token = request.query_params.get("token")
    if token:
        return verify_token(token)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_header_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Authenticate a mutation request only from the Authorization header."""

    if credentials:
        return verify_token(credentials.credentials)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
