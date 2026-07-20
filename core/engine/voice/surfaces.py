"""Voice surface registry.

Each VoiceSurface entry represents a distinct UI/communication channel that
emits text the voice checker should audit. The audit_runner module
iterates this registry to compute consistency scores; new surfaces opt in
by adding a single entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from core.engine.core.db import parse_rows, pool


@dataclass(frozen=True)
class VoiceSurface:
    name: str
    enforce_at_write: bool
    sample_provider: Callable[[str], Awaitable[list[str]]]


async def _briefing_samples(product_id: str) -> list[str]:
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT content, created_at FROM briefing WHERE product = <record>$pid "
                "ORDER BY created_at DESC LIMIT 5",  # SurrealDB v3: ORDER BY field MUST appear in SELECT
                {"pid": product_id},
            )
        )
    return [r["content"] for r in rows if r.get("content")]


async def _proactive_line_samples(product_id: str) -> list[str]:
    # ProactiveLine is a Python dataclass returned by harness.context (not persisted to a table).
    # Sample via the in-memory ring buffer — every emit_proactive_line in stream.py also calls
    # audit_buffer.record("proactive_line", product_id, rendered_text) so the sweeper can drain.
    from core.engine.notifications.audit_buffer import drain_recent

    return drain_recent("proactive_line", product_id)


async def _discord_samples(product_id: str) -> list[str]:
    # Pulls recent in-memory ring buffer + last-week persisted notification rows
    from core.engine.notifications.audit_buffer import drain_recent

    return drain_recent("discord", product_id)


async def _in_app_samples(product_id: str) -> list[str]:
    from core.engine.notifications.audit_buffer import drain_recent

    return drain_recent("in_app", product_id)


async def _session_start_samples(product_id: str) -> list[str]:
    # Hook output is observed via journey_event topic 'session.start.rendered'.
    # IMPORTANT: this topic MUST be registered in engine/cognition/journey_voice.py::_BUS_TOPICS
    # (see §6 below) so the /journey UI doesn't render '[unknown topic: ...]' cards for it.
    # The registered template is short + audit-internal-flavored ("ACE rendered a session footer").
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT payload.context_text AS t, occurred_at FROM journey_event "
                "WHERE topic = 'session.start.rendered' "
                "AND product = <record>$pid AND occurred_at > time::now() - 7d "
                "ORDER BY occurred_at DESC LIMIT 10",  # SurrealDB v3: ORDER BY field MUST appear in SELECT
                {"pid": product_id},
            )
        )
    return [r["t"] for r in rows if r.get("t")]


async def _fixture_samples(kind: str) -> list[str]:
    """Load static fixture text from canonical JSON / Python constants."""
    if kind == "journey":
        from core.engine.cognition.journey_voice import _BUS_TOPICS, _CANVAS_TOPICS

        return list(_CANVAS_TOPICS.values()) + list(_BUS_TOPICS.values())
    if kind == "onboarding":
        from core.engine.onboarding.conversation import COPY

        return (
            [COPY["opening"], COPY["closing_template"]]
            + [q["prompt"] for q in COPY["questions"]]
            + [q["ack_template"] for q in COPY["questions"]]
        )
    return []


async def _journey_template_provider(_: str) -> list[str]:
    return await _fixture_samples("journey")


async def _onboarding_copy_provider(_: str) -> list[str]:
    return await _fixture_samples("onboarding")


async def _drawer_static_provider(_: str) -> list[str]:
    """Sample static user-visible chrome strings from partner-voice/ TSX components.

    Replaces the prior drawer→_briefing_samples alias (which audited dynamic LLM
    output, not static drawer copy). See the static_copy_extractor module for the
    extraction rules. Resolves decision:rre2nyrpv0fih7y69ujr.
    """
    from core.engine.voice.static_copy_extractor import extract_partner_voice_strings

    return extract_partner_voice_strings()


REGISTRY: list[VoiceSurface] = [
    VoiceSurface(name="briefing", enforce_at_write=False, sample_provider=_briefing_samples),
    VoiceSurface(name="proactive_line", enforce_at_write=False, sample_provider=_proactive_line_samples),
    VoiceSurface(name="discord", enforce_at_write=False, sample_provider=_discord_samples),
    VoiceSurface(name="in_app", enforce_at_write=False, sample_provider=_in_app_samples),
    VoiceSurface(name="session_start", enforce_at_write=False, sample_provider=_session_start_samples),
    # Surfaces below are CI-audited only — write-time gates already enforce
    # consistency, so runtime sampling is redundant.
    VoiceSurface(name="journey_templates", enforce_at_write=True, sample_provider=_journey_template_provider),
    VoiceSurface(name="onboarding_copy", enforce_at_write=True, sample_provider=_onboarding_copy_provider),
    VoiceSurface(name="drawer", enforce_at_write=True, sample_provider=_drawer_static_provider),
]
