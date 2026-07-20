"""Portal-router security helpers: ownership Depends + per-product cooldown.

Resolves decision:41esn81p6pdxm51frpbr — portal endpoints accepting `product_id`
as a path param previously skipped any ownership verification, allowing user A
to read/write product B's resources by knowing the ID.

Two helpers:
  - verify_product_access: Depends-shaped auth wrapper that returns 404 (not 403,
    matching engine/core/auth.py:verify_ownership) when the calling user's JWT
    `product` claim doesn't match the path's product_id.
  - enforce_run_cooldown: in-memory per-(endpoint, product) rate limit for write
    endpoints that trigger real compute (e.g., POST /voice-audit/{pid}/run).
    Per-process — restarts reset cooldowns; acceptable for VC-demo scope. Use a
    proper rate-limit infra (Redis, gateway) for prod hardening.
"""

from __future__ import annotations

import time
from threading import Lock

from fastapi import Depends, HTTPException

from core.engine.core.auth import get_current_user

# Module-private cooldown state. Keyed by (endpoint, product_id).
_RUN_COOLDOWN: dict[tuple[str, str], float] = {}
_COOLDOWN_LOCK = Lock()


def verify_product_access(product_id: str, user: dict = Depends(get_current_user)) -> dict:
    """FastAPI Depends: confirms user's JWT `product` claim matches the path's product_id.

    Returns the user dict (so handlers can still use `user=Depends(verify_product_access)`
    in place of `user=Depends(get_current_user)` with no other changes).

    Returns 404 (not 403) on mismatch — mirroring engine/core/auth.py:verify_ownership.
    The 404 choice avoids leaking resource existence to enumeration attackers.

    Note: a missing or empty user.product claim is treated as "no scope check" — this
    preserves existing behavior for tokens issued before the product claim was added.
    Tighten to a 403 once all tokens in flight carry the claim.
    """
    user_product = str(user.get("product", ""))
    if user_product and user_product != product_id:
        raise HTTPException(status_code=404, detail="Not found")
    return user


def enforce_run_cooldown(endpoint: str, product_id: str, min_seconds: int = 30) -> None:
    """Raise 429 if the same (endpoint, product_id) pair was hit within the cooldown window.

    Process-local — see module docstring for the prod-hardening note.
    """
    key = (endpoint, product_id)
    now = time.monotonic()
    with _COOLDOWN_LOCK:
        last = _RUN_COOLDOWN.get(key, 0.0)
        elapsed = now - last
        if elapsed < min_seconds:
            wait = min_seconds - elapsed
            raise HTTPException(
                status_code=429,
                detail=f"Cooldown active — wait {wait:.0f}s before retrying",
                headers={"Retry-After": str(int(wait) + 1)},
            )
        _RUN_COOLDOWN[key] = now


def _reset_cooldown() -> None:
    """Test-only: clear the cooldown map between tests."""
    with _COOLDOWN_LOCK:
        _RUN_COOLDOWN.clear()
