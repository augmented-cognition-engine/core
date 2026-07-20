"""Agent participant identity for the canvas bridge.

One participant per lens (architecture, security, data, ux,
product_strategy, …) plus one for the partner. Identities mirror the
frontend ``disciplineIdentity.ts`` table so the two sides agree on
glyph/accent/role without coordination.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentParticipant:
    """Synthetic agent identity on the board.

    The values map 1:1 to the frontend ``DISCIPLINES`` table in
    ``core/ui/canvas/src/design/disciplineIdentity.ts``. Keep in sync
    when adding a new lens — both sides must agree on glyph and accent.
    """

    id: str
    """Stable id — typically the lens name (``architecture``) or
    ``partner``. Used as the cursor key and shape-id prefix."""

    name: str
    """Display label in the byline (``"Architecture"``, ``"Partner"``)."""

    accent: str
    """CSS color string (hex or ``var(...)``). Drives the lens-accent
    border on the contribution note + the cursor color (if cursors are
    rendered)."""

    glyph: str
    """Single-character identity mark — same family as the participants'
    avatar initials on the PresenceRibbon."""


# Lens accent/glyph values mirror the frontend DISCIPLINES table verbatim.
# Source of truth: core/ui/canvas/src/design/disciplineIdentity.ts §4.1.
LENS_PARTICIPANTS: dict[str, AgentParticipant] = {
    "architecture": AgentParticipant(id="architecture", name="Architecture", accent="#5B7A99", glyph="⌂"),
    "security": AgentParticipant(id="security", name="Security", accent="#8C3A3A", glyph="◉"),
    "data": AgentParticipant(id="data", name="Data", accent="#5F7A4F", glyph="≈"),
    "ux": AgentParticipant(id="ux", name="UX", accent="#C26648", glyph="◐"),
    "product_strategy": AgentParticipant(
        id="product_strategy",
        name="Product Strategy",
        accent="#C49348",
        glyph="◆",
    ),
    "performance": AgentParticipant(id="performance", name="Performance", accent="#B07238", glyph="→"),
    "ai_ml": AgentParticipant(id="ai_ml", name="AI/ML", accent="#B47274", glyph="✦"),
}

PARTNER_PARTICIPANT = AgentParticipant(
    id="partner",
    name="Partner",
    accent="var(--ace-accent)",  # resolves to engineered-light electric blue
    glyph="◇",
)


def get_participant(lens_or_id: str) -> AgentParticipant:
    """Return the participant for a lens id, or the partner for ``partner``.

    Unknown ids fall back to a neutral ``voice`` participant so the
    surface never refuses to render.
    """
    if lens_or_id == "partner":
        return PARTNER_PARTICIPANT
    if lens_or_id in LENS_PARTICIPANTS:
        return LENS_PARTICIPANTS[lens_or_id]
    return AgentParticipant(id=lens_or_id, name=lens_or_id.title(), accent="#8A8175", glyph="·")
