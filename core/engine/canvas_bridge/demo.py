"""Scripted deliberation demo — drives the Phase 4 acceptance criteria.

Run via the ``POST /canvas/demo/deliberate/{room_id}`` endpoint defined
in :mod:`core.engine.canvas_bridge.api`. Spawns a background task that
walks five lens voices through a staged deliberation over ~12 seconds:

  t≈0s   architecture lands (cache-layer assumption)
  t≈2s   security lands (auth-token revalidation window)
  t≈4s   data lands (calibration regime shift)
  t≈6s   ux appears in-flight (asymmetric landing)
  t≈11s  ux lands

The content mirrors the multiplayer fixture so the demo reads as a
direct continuation of that scene — the user can see the team
deliberating from where the fixture left off, with agents now driving
shape creation rather than the seed function.
"""

from __future__ import annotations

import asyncio
from logging import getLogger

from core.engine.canvas_bridge.bridge import (
    AgentContribution,
    bridge,
)
from core.engine.canvas_bridge.messages import (
    AgentChatMessage,
    agent_note,
    attention_request,
)
from core.engine.canvas_bridge.participant import (
    PARTNER_PARTICIPANT,
    get_participant,
)

logger = getLogger(__name__)


async def run_scripted_deliberation(room_id: str) -> None:
    """Run the scripted demo. Idempotent per-id: contributions from a
    prior run are cleared before the new run starts."""
    b = bridge()

    logger.info("demo: starting scripted deliberation in room=%s", room_id)
    await b.clear_contributions(room_id)
    await b.clear_all_cursors(room_id)
    await b.clear_messages(room_id)

    # Register the user-reply responder before any attention requests
    # are posted. The responder fires once per user reply — its handler
    # acknowledges in chat AND drops a follow-up note on the board so
    # the partnership channel reads as bidirectional (Phase 5 acceptance).
    b.observe_user_replies(room_id, _make_reply_handler(room_id))

    layout = b.default_position

    # ── beat 1: architecture lands ─────────────────────────────────────
    arch = get_participant("architecture")
    await b.set_cursor(
        room_id,
        arch,
        layout("architecture")["x"] + 140,
        layout("architecture")["y"] + 100,
        activity="forming the cache-layer read",
    )
    await asyncio.sleep(0.4)
    await b.add_contribution(
        room_id,
        AgentContribution(
            id="agent-architecture",
            lens="architecture",
            speaker=arch.name,
            accent=arch.accent,
            framing=(
                "The cache-layer assumption is shaky at 50 RPS. The y-axis "
                "is fixed at memory pressure, but the real constraint is "
                "eviction tail-latency — and that doesn't hold linearly "
                "past the threshold."
            ),
            in_flight=False,
            landed_at="just now",
            **layout("architecture"),
        ),
    )

    await asyncio.sleep(1.8)

    # ── beat 2: security lands ─────────────────────────────────────────
    sec = get_participant("security")
    await b.set_cursor(
        room_id,
        sec,
        layout("security")["x"] + 140,
        layout("security")["y"] + 100,
        activity="weighing the auth-revalidation window",
    )
    await asyncio.sleep(0.4)
    await b.add_contribution(
        room_id,
        AgentContribution(
            id="agent-security",
            lens="security",
            speaker=sec.name,
            accent=sec.accent,
            framing=(
                "If we defer the cache, the auth-token revalidation window "
                "grows. It's not a breach risk — it's a measurable "
                "degradation in the trust window. Worth flagging, not "
                "worth blocking."
            ),
            in_flight=False,
            landed_at="just now",
            **layout("security"),
        ),
    )

    await asyncio.sleep(1.8)

    # ── beat 3: data lands ─────────────────────────────────────────────
    data = get_participant("data")
    await b.set_cursor(
        room_id,
        data,
        layout("data")["x"] + 140,
        layout("data")["y"] + 100,
        activity="reading the calibration curve",
    )
    await asyncio.sleep(0.4)
    await b.add_contribution(
        room_id,
        AgentContribution(
            id="agent-data",
            lens="data",
            speaker=data.name,
            accent=data.accent,
            framing=(
                "The Y-shape break in the calibration curve is a real "
                "regime shift, not instrumentation noise. Traffic "
                "distribution moved from long-tail to bimodal over the "
                "last nine days."
            ),
            in_flight=False,
            landed_at="just now",
            **layout("data"),
        ),
    )

    await asyncio.sleep(1.8)

    # ── beat 4: ux appears in-flight ───────────────────────────────────
    ux = get_participant("ux")
    await b.set_cursor(
        room_id,
        ux,
        layout("ux")["x"] + 140,
        layout("ux")["y"] + 120,
        activity="examining the asymmetric landing",
    )
    await asyncio.sleep(0.4)
    await b.add_contribution(
        room_id,
        AgentContribution(
            id="agent-ux",
            lens="ux",
            speaker=ux.name,
            accent=ux.accent,
            framing=(
                "Given the bimodal traffic, the cache-layer change lands "
                "asymmetrically. Power users see the wins; casual users "
                "see only the latency-floor drop. We'd be optimizing for "
                "one tail of the distribution — and the casual tail is "
                "where the trust"
            ),
            in_flight=True,
            thinking_about=("whether casual-user latency-floor drop is worse than the asymmetric win"),
            **layout("ux"),
        ),
    )

    # ── partner moves to the chat-panel area, marks attention ──────────
    partner_pos = layout("partner")
    await b.set_cursor(
        room_id,
        PARTNER_PARTICIPANT,
        partner_pos["x"] + 60,
        partner_pos["y"] + 80,
        activity="holding for your call",
    )

    # UX deliberates for ~5s, then lands.
    await asyncio.sleep(5.0)
    await b.update_contribution(
        room_id,
        "agent-ux",
        framing=(
            "Given the bimodal traffic, the cache-layer change lands "
            "asymmetrically. Power users see the wins; casual users see "
            "only the latency-floor drop. We'd be optimizing for one "
            "tail of the distribution — and the casual tail is where "
            "the trust window matters most. Recommend we hold."
        ),
        in_flight=False,
        landed_at="just now",
        thinking_about=None,
    )
    await b.clear_cursor(room_id, "ux")

    # ── beat 5: partner posts an attention request in the chat panel ──
    # Phase 5 acceptance: the partner addresses the user directly via
    # the chat panel, with question + inline ask-back input.
    await asyncio.sleep(0.6)
    await b.post_message(
        room_id,
        attention_request(
            PARTNER_PARTICIPANT,
            body=(
                "Heads up — UX landed on hold, but the call hinges on "
                "how much you weight the casual-user tail. I think this "
                "is the load-bearing decision. Want to put your thumb on "
                "the scale, or trust the team to ship the hold?"
            ),
            triggered_by=("UX confidence at 0.62 — below the 0.70 threshold I usually let through unattended"),
        ),
    )

    logger.info("demo: deliberation complete in room=%s", room_id)


def _make_reply_handler(room_id: str):
    """Return an async callback that the bridge fires whenever a user
    reply lands in the chat. The handler acknowledges in chat AND drops
    a partner-driven follow-up note on the board so the round-trip is
    visibly bidirectional."""

    async def handler(msg: AgentChatMessage) -> None:
        b = bridge()
        logger.info("demo: user reply received (room=%s body=%r)", room_id, msg.body[:60])

        # Acknowledge in the chat panel.
        await b.post_message(
            room_id,
            agent_note(
                PARTNER_PARTICIPANT,
                body=(
                    f"Got it. Folding “{msg.body.strip()}” into the call — "
                    "I'll drop a follow-up note on the board so the team sees the "
                    "decision land."
                ),
            ),
        )

        # Drop a follow-up shape on the board so the loop is visible
        # spatially as well as in the chat log.
        partner_layout = b.default_position("partner")
        await b.add_contribution(
            room_id,
            AgentContribution(
                id="agent-partner-followup",
                lens="voice",
                speaker=PARTNER_PARTICIPANT.name,
                accent=PARTNER_PARTICIPANT.accent,
                framing=("You weighed in: hold confirmed. Closing the loop and capturing the call to memory."),
                in_flight=False,
                landed_at="just now",
                **partner_layout,
            ),
        )

    return handler
