# tests/test_auth.py
from datetime import timedelta

import pytest
from fastapi import HTTPException


def test_create_and_verify_token():
    from core.engine.core.auth import create_access_token, verify_token

    token = create_access_token({"sub": "user:test123"})
    assert isinstance(token, str)
    assert len(token) > 20

    payload = verify_token(token)
    assert payload["sub"] == "user:test123"


def test_verify_invalid_token_raises():
    from core.engine.core.auth import verify_token

    with pytest.raises(HTTPException) as exc:
        verify_token("not-a-real-token")
    assert exc.value.status_code == 401


def test_verify_expired_token_raises():
    from core.engine.core.auth import create_access_token, verify_token

    token = create_access_token({"sub": "user:x"}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401
