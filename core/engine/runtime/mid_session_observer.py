"""Mid-session observer — Tier 2 of the capture pipeline.

Scans the last N turns every `scan_interval` assistant messages.
Uses Haiku to classify high-signal moments (decisions, errors,
discoveries, patterns) and writes them directly to the ACE graph
via ace_capture — bypassing the event queue for near-real-time writes.

Three capture tiers (per spec):
  Tier 1 — Immediate: model explicitly calls ace_graph_capture / ace_graph_decision
  Tier 2 — Near-real-time: THIS MODULE — Haiku scan every scan_interval turns
  Tier 3 — Batch: AutoExtractor fires at session end via event pipeline

Fire-and-forget: never blocks the next user turn.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.engine.runtime.models import Message

logger = logging.getLogger(__name__)

_SCAN_PROMPT = """\
You are analyzing a software development conversation to extract high-signal observations.

Review the turns below. For EACH significant moment, classify it as:
- decision: a technical or architectural choice was made (chose X over Y, not just exploration)
- error: something broken was identified, debugged, or fixed
- discovery: a non-obvious insight about how the codebase or system actually works
- pattern: a recurring approach or convention emerged

LOW signal = skip (greetings, status checks, "what's next", routine tasks).
HIGH signal = decisions with rationale, bugs found/fixed, surprising behavior, design principles.

Domain must be one of: security, testing, ux, performance, devops, data, accessibility,
documentation, ai_ml, architecture, api_design, data_modeling, business_logic, integration,
error_handling, observability, configuration, deployment, versioning, scale,
code_conventions, dependency_management

Return ONLY valid JSON, no markdown:
{{"findings": [{{"type": "decision|error|discovery|pattern", "content": "...", "domain": "...", "confidence": 0.0}}]}}

If nothing significant, return {{"findings": []}}.

Conversation:
{excerpt}"""

_MIN_EXCERPT_CHARS = 200
_DEFAULT_SCAN_INTERVAL = 5
_WINDOW_TURNS = 10  # how many turns to include in each scan


class MidSessionObserver:
    """Haiku-powered mid-session signal scanner.

    Parameters
    ----------
    product_id:
        ACE product to write observations to.
    scan_interval:
        Number of assistant turns between scans. Default: 5.
    """

    def __init__(
        self,
        product_id: str = "product:platform",
        scan_interval: int = _DEFAULT_SCAN_INTERVAL,
    ) -> None:
        self._product_id = product_id
        self._scan_interval = scan_interval
        self._turn_count = 0
        self._pending: asyncio.Task | None = None

    def record_turn(self, messages: list[Message]) -> None:
        """Call after each assistant turn completes.

        Increments the turn counter and schedules a scan when the interval
        is reached. Fire-and-forget — does not block the caller.
        """
        self._turn_count += 1
        if self._turn_count % self._scan_interval == 0:
            self._fire(messages)

    def _fire(self, messages: list[Message]) -> None:
        """Schedule a scan without blocking."""
        try:
            loop = asyncio.get_running_loop()
            if self._pending and not self._pending.done():
                # Previous scan still running — skip this cycle rather than queue
                logger.debug("MidSessionObserver: previous scan still running, skipping")
                return
            self._pending = loop.create_task(self._scan(list(messages)))
        except RuntimeError:
            logger.debug("MidSessionObserver: no event loop, skipping scan")

    async def _scan(self, messages: list[Message]) -> None:
        """Run Haiku classification on the last _WINDOW_TURNS turns."""
        from core.engine.runtime.models import AssistantMessage, UserMessage

        # Build sliding window — last _WINDOW_TURNS user/assistant pairs
        relevant = [
            m for m in messages if isinstance(m, (UserMessage, AssistantMessage)) and not getattr(m, "is_meta", False)
        ]
        window = relevant[-(_WINDOW_TURNS * 2) :]  # *2 because each turn = user + assistant

        if not window:
            return

        excerpt = "\n".join(
            f"{'User' if isinstance(m, UserMessage) else 'Assistant'}: {m.content[:500]}" for m in window
        )

        if len(excerpt) < _MIN_EXCERPT_CHARS:
            return

        try:
            from core.engine.core.llm import get_llm
            from core.engine.runtime.model_config import route_model

            model = route_model("mid_session_scan")
            result = await get_llm().complete_json(
                _SCAN_PROMPT.format(excerpt=excerpt),
                model=model,
                max_tokens=512,
            )
        except Exception as exc:
            logger.debug("MidSessionObserver scan LLM call failed: %s", exc)
            return

        findings = result.get("findings", []) if isinstance(result, dict) else []
        if not findings:
            return

        await self._write_findings(findings)

    async def _write_findings(self, findings: list[dict]) -> None:
        """Write each high-signal finding directly to the ACE graph."""
        try:
            from core.engine.mcp.tools import ace_capture
        except ImportError:
            logger.debug("MidSessionObserver: ace_capture not available")
            return

        valid_types = {"decision", "error", "discovery", "pattern", "learning", "correction"}

        for finding in findings:
            obs_type = finding.get("type", "")
            content = finding.get("content", "")
            domain = finding.get("domain", "architecture")
            confidence = float(finding.get("confidence", 0.7))

            if not content or obs_type not in valid_types:
                continue

            # Map discovery → learning (ace_capture's accepted types)
            if obs_type == "discovery":
                obs_type = "learning"

            try:
                await ace_capture(
                    observation_type=obs_type,
                    content=content,
                    domain_path=domain,
                    confidence=confidence,
                    product_id=self._product_id,
                )
                logger.debug(
                    "MidSessionObserver: captured %s in %s (confidence=%.2f)",
                    obs_type,
                    domain,
                    confidence,
                )
            except Exception as exc:
                logger.debug("MidSessionObserver: ace_capture failed: %s", exc)

    @property
    def turn_count(self) -> int:
        """Number of assistant turns seen this session."""
        return self._turn_count
