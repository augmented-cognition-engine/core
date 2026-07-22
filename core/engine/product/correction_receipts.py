"""Bounded lifecycle helpers for durable correction projections."""

from __future__ import annotations

from datetime import datetime, timezone


def effective_correction_lifecycle(
    lifecycle_state: str | None,
    expires_at: datetime | str | None,
    *,
    now: datetime | None = None,
) -> str | None:
    """Project expiry without overwriting or deleting the stored correction."""
    if lifecycle_state != "active" or expires_at is None:
        return lifecycle_state
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return lifecycle_state
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return "expired" if expires_at <= reference else lifecycle_state
