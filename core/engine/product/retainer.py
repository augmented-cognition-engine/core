# engine/product/retainer.py
"""RetainerTracker — turns one-time deliveries into retainer conversations.

After a spec is delivered and verified, RetainerTracker surfaces the next
automation to pitch. Keeps engagement alive without the operator having to
remember to follow up.

Components:
  EngagementState        — append-only delivery + verification history
  ExpansionRecommendation — what was built, what's next, ROI, retainer framing
  RetainerTracker        — orchestrates state + expansion recommendations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from core.engine.product.report_models import DiscoveryReport

logger = logging.getLogger(__name__)


@dataclass
class EngagementState:
    """Append-only record of deliveries and verifications for a client engagement.

    Immutable by convention: deliveries and verifications are never overwritten.
    Each call to record_delivery/record_verification appends a new entry.
    """

    product_id: str
    deliveries: List[dict] = field(default_factory=list)
    verifications: List[dict] = field(default_factory=list)

    def record_delivery(self, spec_id: str, title: str) -> None:
        """Append a delivery record — immutable, never overwrites."""
        self.deliveries.append(
            {
                "spec_id": spec_id,
                "title": title,
                "status": "delivered",
            }
        )

    def record_verification(self, spec_id: str, passed: bool) -> None:
        """Append a verification record — immutable, never overwrites."""
        self.verifications.append(
            {
                "spec_id": spec_id,
                "passed": passed,
            }
        )

    def delivered_titles(self) -> List[str]:
        """Return the list of delivered spec titles."""
        return [d["title"] for d in self.deliveries]

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "deliveries": list(self.deliveries),
            "verifications": list(self.verifications),
        }


@dataclass
class ExpansionRecommendation:
    """Retainer expansion pitch: what was built, what's next, ROI framing."""

    product_id: str
    delivered_specs: List[str]  # titles of delivered work
    next_title: str
    next_description: str
    next_annual_value: float
    retainer_framing: str  # "We automated X, here's Y which unlocks Z"

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "delivered_specs": self.delivered_specs,
            "next_title": self.next_title,
            "next_description": self.next_description,
            "next_annual_value": self.next_annual_value,
            "retainer_framing": self.retainer_framing,
        }


class RetainerTracker:
    """Tracks engagement state and surfaces the next retainer expansion.

    Usage::

        tracker = RetainerTracker(product_id="product:acme")
        tracker.record_delivery(spec_id="agent_spec:abc", title="Auth middleware")
        rec = tracker.next_expansion(discovery_report=report)
        print(rec.retainer_framing)
    """

    def __init__(self, product_id: str) -> None:
        self.product_id = product_id
        self.engagement_state = EngagementState(product_id=product_id)

    def record_delivery(self, spec_id: str, title: str) -> None:
        """Record a delivered spec — updates engagement state."""
        self.engagement_state.record_delivery(spec_id=spec_id, title=title)
        logger.info(
            "RetainerTracker: delivery recorded for %s — %s",
            self.product_id,
            title,
        )

    def next_expansion(
        self,
        discovery_report: Optional["DiscoveryReport"],
    ) -> Optional[ExpansionRecommendation]:
        """Return the highest-priority undelivered automation candidate.

        Args:
            discovery_report: The original discovery sprint report (provides the
                              ranked automation candidate list). Pass None to fall
                              back to a generic recommendation.

        Returns:
            ExpansionRecommendation if there is an undelivered candidate,
            None if all candidates have been delivered.
        """
        delivered_titles = set(self.engagement_state.delivered_titles())

        if discovery_report is None:
            return self._fallback_expansion(delivered_titles)

        # Find the first undelivered candidate (candidates are already priority-ordered)
        next_candidate = None
        for candidate in discovery_report.automation_candidates:
            if candidate.title not in delivered_titles:
                next_candidate = candidate
                break

        if next_candidate is None:
            return None  # All candidates delivered

        return self._build_recommendation(
            next_candidate=next_candidate,
            delivered_titles=list(delivered_titles),
            discovery_report=discovery_report,
        )

    # ── Private builders ──────────────────────────────────────────────────────

    def _build_recommendation(
        self,
        next_candidate,
        delivered_titles: List[str],
        discovery_report: "DiscoveryReport",
    ) -> ExpansionRecommendation:
        """Build a retainer recommendation from an automation candidate."""
        framing = self._build_framing(
            delivered_titles=delivered_titles,
            next_candidate=next_candidate,
        )

        return ExpansionRecommendation(
            product_id=self.product_id,
            delivered_specs=delivered_titles,
            next_title=next_candidate.title,
            next_description=next_candidate.description,
            next_annual_value=next_candidate.annual_value,
            retainer_framing=framing,
        )

    def _build_framing(self, delivered_titles: List[str], next_candidate) -> str:
        """Build retainer framing: 'We automated X, here's Y which unlocks Z'."""
        if delivered_titles:
            last_delivered = delivered_titles[-1]
            return (
                f"We automated {last_delivered.lower()}, which is now saving "
                f"{next_candidate.hours_per_week_saved:.0f}+ hours per week. "
                f"The natural next step is {next_candidate.title.lower()} — "
                f"worth ${next_candidate.annual_value:,.0f}/year — "
                f"which builds directly on what we've already delivered."
            )
        return (
            f"The highest-priority automation is {next_candidate.title.lower()}, "
            f"worth ${next_candidate.annual_value:,.0f}/year. "
            f"This is the best starting point based on ROI and effort."
        )

    def _fallback_expansion(self, delivered_titles: set) -> ExpansionRecommendation:
        """Fallback when no discovery report is available."""
        delivered_list = list(delivered_titles)
        return ExpansionRecommendation(
            product_id=self.product_id,
            delivered_specs=delivered_list,
            next_title="Run discovery sprint",
            next_description=(
                "A discovery sprint will identify and prioritize the next "
                "automation opportunity with grounded ROI estimates."
            ),
            next_annual_value=0.0,
            retainer_framing=(
                f"We've delivered {len(delivered_list)} automation(s) so far. "
                "Running a discovery sprint will surface the next highest-value opportunity."
            ),
        )
