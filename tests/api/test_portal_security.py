"""Regression tests for portal-router security helpers.

Pins the verify_product_access + enforce_run_cooldown contract so the IDOR
fix (decision:41esn81p6pdxm51frpbr) doesn't silently regress.
"""

from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from core.engine.api._portal_security import (
    _reset_cooldown,
    enforce_run_cooldown,
    verify_product_access,
)


def test_verify_product_access_allows_matching_product():
    user = {"product": "product:platform"}
    result = verify_product_access("product:platform", user=user)
    assert result is user  # passes through user dict


def test_verify_product_access_404s_on_mismatch():
    user = {"product": "product:tenant_a"}
    with pytest.raises(HTTPException) as exc_info:
        verify_product_access("product:tenant_b", user=user)
    assert exc_info.value.status_code == 404
    # Must NOT 403 — that would leak resource existence to enumeration attackers.
    assert "Not found" in exc_info.value.detail


def test_verify_product_access_passes_when_token_has_no_product_claim():
    """Backwards-compat: tokens issued before the product claim was added."""
    user = {"email": "legacy@example.com"}  # no 'product' key
    result = verify_product_access("product:any_value", user=user)
    assert result is user


def test_cooldown_first_call_passes():
    _reset_cooldown()
    enforce_run_cooldown("test_endpoint", "product:test", min_seconds=30)


def test_cooldown_second_call_within_window_429s():
    _reset_cooldown()
    enforce_run_cooldown("test_endpoint", "product:test", min_seconds=30)
    with pytest.raises(HTTPException) as exc_info:
        enforce_run_cooldown("test_endpoint", "product:test", min_seconds=30)
    assert exc_info.value.status_code == 429
    assert "Cooldown active" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers


def test_cooldown_isolated_per_endpoint():
    """Calls to endpoint A don't block calls to endpoint B."""
    _reset_cooldown()
    enforce_run_cooldown("endpoint_a", "product:test", min_seconds=30)
    enforce_run_cooldown("endpoint_b", "product:test", min_seconds=30)  # should not raise


def test_cooldown_isolated_per_product():
    """Calls for product A don't block calls for product B."""
    _reset_cooldown()
    enforce_run_cooldown("test_endpoint", "product:a", min_seconds=30)
    enforce_run_cooldown("test_endpoint", "product:b", min_seconds=30)  # should not raise


def test_cooldown_passes_after_window_elapses():
    _reset_cooldown()
    enforce_run_cooldown("test_endpoint", "product:test", min_seconds=0)  # zero-second window
    time.sleep(0.01)
    # min_seconds=0 means any elapsed time satisfies the gate
    enforce_run_cooldown("test_endpoint", "product:test", min_seconds=0)
