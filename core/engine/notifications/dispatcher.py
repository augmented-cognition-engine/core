"""Notification dispatcher — create and deliver tiered notifications.

Four tiers: critical (push + banner), actionable (Home attention),
informational (activity feed), silent (log only).

Error handling:
- Dispatch failures are caught, logged, and queued for retry.
- Retry logic uses exponential backoff with configurable limits.
- Failed notifications are never silently lost — they are logged
  with full context (timestamp, notification ID, error details).
- Dispatch failures do not propagate to callers; triggers always
  get a result dict back (possibly a fallback stub).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from core.engine.core.db import pool
from core.engine.notifications.channels import channel_registry

logger = logging.getLogger(__name__)

# Default delivery channels per tier.
# Channels not registered at runtime are silently skipped.
DEFAULT_CHANNELS = {
    "critical": ["in_app", "discord", "webhook"],
    "actionable": ["in_app", "discord"],
    "informational": ["in_app"],
    "silent": [],
}

# ---------------------------------------------------------------------------
# Retry configuration — all values are module-level so callers can override
# them in tests or via settings without patching internals.
# ---------------------------------------------------------------------------
RETRY_MAX_ATTEMPTS: int = 3  # maximum dispatch attempts (1 original + N-1 retries)
RETRY_BASE_DELAY: float = 1.0  # seconds before first retry
RETRY_MAX_DELAY: float = 30.0  # cap on exponential backoff


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff capped at RETRY_MAX_DELAY.

    attempt=0 → base_delay, attempt=1 → base_delay*2, ...
    """
    delay = RETRY_BASE_DELAY * (2**attempt)
    return min(delay, RETRY_MAX_DELAY)


def _log_dispatch_failure(
    *,
    attempt: int,
    max_attempts: int,
    product_id: str,
    user_id: str,
    tier: str,
    category: str,
    title: str,
    error: Exception,
    notification_id: str | None = None,
) -> None:
    """Emit a structured ERROR log for a failed dispatch attempt."""
    logger.error(
        "Notification dispatch failed | timestamp=%s attempt=%d/%d "
        "notification_id=%s org=%s user=%s tier=%s category=%s title=%r error=%s: %s",
        datetime.now(timezone.utc).isoformat(),
        attempt,
        max_attempts,
        notification_id or "pending",
        product_id,
        user_id,
        tier,
        category,
        title,
        type(error).__name__,
        error,
    )


async def _attempt_dispatch(
    product_id: str,
    user_id: str,
    tier: str,
    category: str,
    title: str,
    body: str | None,
    link: str | None,
    source_record: str | None,
    workspace_id: str | None,
    channels: list[str],
    project_id: str | None = None,
) -> dict:
    """Single attempt to persist a notification record.  Raises on failure."""
    project_clause = "project = <record>$project," if project_id else ""
    async with pool.connection() as db:
        params = {
            "product": product_id,
            "user": user_id,
            "workspace": workspace_id,
            "tier": tier,
            "category": category,
            "title": title,
            "body": body,
            "link": link,
            "source_record": source_record,
            "channels": channels,
        }
        if project_id:
            params["project"] = project_id
        result = await db.query(
            f"""
            CREATE notification SET
                user = <record>$user,
                {project_clause}
                tier = $tier,
                category = $category,
                title = $title,
                body = $body,
                link = $link,
                source_record = $source_record,
                delivered_via = $channels,
                created_at = time::now()
            """,
            params,
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])

    return rows[0] if rows else {}


async def dispatch(
    product_id: str,
    user_id: str,
    tier: str,
    category: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    source_record: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Create a notification and deliver to appropriate channels.

    Returns the created notification record.  Never raises — dispatch
    failures are caught, logged, retried with exponential backoff, and
    a fallback stub is returned when all attempts are exhausted.
    """
    channels = DEFAULT_CHANNELS.get(tier, ["in_app"])

    # -----------------------------------------------------------------------
    # Load user preferences — failure is non-fatal; fall back to defaults.
    # -----------------------------------------------------------------------
    try:
        async with pool.connection() as db:
            pref_result = await db.query(
                """
                SELECT channels, enabled FROM notification_pref
                WHERE product = <record>$product AND user = <record>$user AND tier = $tier
                LIMIT 1
                """,
                {"product": product_id, "user": user_id, "tier": tier},
            )
            pref_rows = pref_result[0] if pref_result and isinstance(pref_result[0], list) else (pref_result or [])
            if pref_rows and pref_rows[0].get("enabled", True):
                channels = pref_rows[0].get("channels", channels)
    except Exception as exc:
        logger.warning("Failed to load notification prefs: %s", exc)

    # -----------------------------------------------------------------------
    # Dispatch with retry + exponential backoff.
    # -----------------------------------------------------------------------
    last_exc: Exception | None = None

    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            notification = await _attempt_dispatch(
                product_id=product_id,
                user_id=user_id,
                tier=tier,
                category=category,
                title=title,
                body=body,
                link=link,
                source_record=source_record,
                workspace_id=workspace_id,
                channels=channels,
                project_id=project_id,
            )
            # Success — fill in defaults if the DB row came back empty.
            if not notification:
                notification = {"tier": tier, "category": category, "title": title}
            logger.info("Notification dispatched: [%s] %s — %s", tier, category, title)

            # --- External channel delivery (fire-and-forget) ---
            for ch_name in channels:
                if ch_name == "in_app":
                    continue  # already handled by DB write
                ch = channel_registry.get(ch_name)
                if ch is None:
                    logger.warning("Channel %r not registered, skipping", ch_name)
                    continue
                try:
                    await ch.send(notification)
                except Exception as ch_exc:
                    logger.warning(
                        "Channel %r delivery failed for notification %s: %s",
                        ch_name,
                        notification.get("id", "?"),
                        ch_exc,
                    )

            return notification

        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _log_dispatch_failure(
                attempt=attempt,
                max_attempts=RETRY_MAX_ATTEMPTS,
                product_id=product_id,
                user_id=user_id,
                tier=tier,
                category=category,
                title=title,
                error=exc,
            )

            if attempt < RETRY_MAX_ATTEMPTS:
                delay = _backoff_delay(attempt - 1)
                logger.info(
                    "Retrying notification dispatch in %.1fs (attempt %d/%d) tier=%s category=%s",
                    delay,
                    attempt + 1,
                    RETRY_MAX_ATTEMPTS,
                    tier,
                    category,
                )
                await asyncio.sleep(delay)

    # -----------------------------------------------------------------------
    # All attempts exhausted — return a fallback stub so callers are not
    # blocked and notification data is preserved in the log record.
    # -----------------------------------------------------------------------
    logger.error(
        "Notification permanently failed after %d attempts | "
        "timestamp=%s org=%s user=%s tier=%s category=%s title=%r last_error=%s: %s",
        RETRY_MAX_ATTEMPTS,
        datetime.now(timezone.utc).isoformat(),
        product_id,
        user_id,
        tier,
        category,
        title,
        type(last_exc).__name__ if last_exc else "unknown",
        last_exc,
    )
    return {
        "tier": tier,
        "category": category,
        "title": title,
        "_dispatch_failed": True,
        "_error": str(last_exc),
    }
