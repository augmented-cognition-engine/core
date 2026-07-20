# engine/product/conversation.py
"""Conversational PM — detect product intents from chat and route to product modules.

Detects these intents:
- "what should I work on?" → ProductPrioritizer
- "scan my repo" / "scan the codebase" → CapabilityMapper bootstrap
- "what's the state of X?" / "show me X" → ProductMap.get_capability
- "what are my gaps?" → quality gaps query
- "set direction to X" → ProductMap.set_vision
- "fix that" / "generate spec for X" → SpecGenerator
- "product health" / "how's the product?" → ProductMap.health_summary

Falls through to regular chat handler for non-product intents.
"""

import logging
import re

from core.engine.core.db import parse_rows
from core.engine.product.map import ProductMap
from core.engine.product.prioritizer import ProductPrioritizer

logger = logging.getLogger(__name__)

# Intent patterns — order matters (first match wins).
# "first_only" patterns only match on the FIRST message in a conversation;
# they are too broad and would swallow normal follow-ups in multi-turn.
INTENT_PATTERNS: list[tuple[str, str, bool]] = [
    # (pattern, intent_name, first_message_only?)
    (r"(?:what should i|what to) work on", "prioritize", False),
    (r"(?:scan|analyze|index) (?:my |the )?(?:repo|codebase|code)", "scan", False),
    (r"(?:product )?health|how.s the product", "health", False),
    (r"(?:what are|show(?: me)?|list) (?:my |the )?gaps\b", "gaps", False),
    (r"(?:state of|status of|show me) (.+)", "capability_detail", True),
    (r"(?:tell me about|describe|explain|what is) (.+)", "lookup", True),
    (r"set direction (?:to )?(.+)", "set_direction", False),
    (r"(?:fix|generate spec|write spec|create spec)(?: for)? (.+)", "generate_spec", False),
    (r"(?:show |list )?(?:my )?(?:backlog|ideas)", "list_ideas", False),
]


class ProductConversation:
    """Route product-level chat intents to the right modules."""

    def __init__(self, db_pool):
        self._pool = db_pool
        self._product_map = ProductMap(db_pool)

    async def detect_intent(self, message: str, is_first_message: bool = True) -> dict | None:
        """Detect if a message has a product-level intent.

        Args:
            message: The user message.
            is_first_message: True if this is the first message in the session.
                Broad patterns (lookup, capability_detail) only match on first
                message to avoid swallowing normal follow-ups in multi-turn.

        Returns {intent: str, params: dict} or None if no product intent.
        """
        msg_lower = message.lower().strip()

        for pattern, intent, first_only in INTENT_PATTERNS:
            if first_only and not is_first_message:
                continue
            match = re.search(pattern, msg_lower)
            if match:
                params = {}
                if match.groups():
                    params["query"] = match.group(1).strip()
                return {"intent": intent, "params": params}

        return None

    async def handle_product_intent(self, intent: dict, product_id: str) -> dict:
        """Handle a detected product intent and return structured response.

        Returns {response: str, data: dict, handled: bool}
        """
        intent_type = intent.get("intent")
        params = intent.get("params", {})

        if intent_type == "health":
            health = await self._product_map.health_summary(product_id)
            total = health.get("total_capabilities", 0)
            dims = health.get("dimensions", {})
            worst = sorted(dims.items(), key=lambda x: x[1].get("avg_score", 1))[:3]
            summary = ", ".join(f"{d}: {v['avg_score']:.0%}" for d, v in worst)
            return {
                "response": f"Product has {total} capabilities. Weakest areas: {summary}.",
                "data": health,
                "handled": True,
            }

        elif intent_type == "gaps":
            async with self._pool.connection() as db:
                result = await db.query(
                    "SELECT * FROM capability_quality WHERE product = <record>$product AND score < 0.4 ORDER BY score LIMIT 10",
                    {"product": product_id},
                )
                gaps = parse_rows(result)
            gap_count = len(gaps)
            top_gaps = gaps[:3]
            summary = "\n".join(f"- {g.get('dimension', '?')}: score {g.get('score', 0):.1f}" for g in top_gaps)
            return {
                "response": f"Found {gap_count} critical gaps (score < 0.4):\n{summary}",
                "data": {"gaps": gaps, "count": gap_count},
                "handled": True,
            }

        elif intent_type == "prioritize":
            prioritizer = ProductPrioritizer(self._pool)
            recs = await prioritizer.prioritize(product_id)
            top = recs[:5]
            summary = "\n".join(
                f"{i + 1}. {r.get('capability_slug', '?')}/{r.get('dimension', '?')} — score {r.get('current_score', 0):.1f}"
                for i, r in enumerate(top)
            )
            return {
                "response": f"Top {len(top)} recommendations:\n{summary}",
                "data": {"recommendations": top},
                "handled": True,
            }

        elif intent_type == "capability_detail":
            query = params.get("query", "")
            # Try to match a capability slug
            slug = query.replace(" ", "_").lower()
            cap = await self._product_map.get_capability(slug, product_id)
            if cap:
                quality = cap.get("quality", {})
                quality_summary = (
                    ", ".join(f"{d}: {v.get('score', 0):.1f}" for d, v in quality.items())
                    if quality
                    else "not yet assessed"
                )
                return {
                    "response": f"**{cap.get('name', slug)}** ({cap.get('status', '?')})\n{cap.get('description', '')}\nQuality: {quality_summary}",
                    "data": cap,
                    "handled": True,
                }
            # Nothing found — fall through to full orchestration
            return {"response": "", "data": {}, "handled": False}

        elif intent_type == "set_direction":
            direction_text = params.get("query", "")
            if direction_text:
                result = await self._product_map.set_vision(
                    {"name": direction_text, "description": direction_text},
                    product_id,
                )
                return {
                    "response": f"Direction set: {direction_text}",
                    "data": result,
                    "handled": True,
                }

        elif intent_type == "scan":
            return {
                "response": "Starting capability scan from code graph...",
                "data": {"action": "scan_requested"},
                "handled": True,
            }

        elif intent_type == "generate_spec":
            description = params.get("query", "")
            # artifact_id is None here because this handler signals intent only;
            # actual spec creation happens via SpecGenerator called by the chat handler.
            # When a spec is created, artifact_id and artifact_type must be present so
            # the caller can create a `produced` edge.
            return {
                "response": f"Generating spec for: {description}",
                "data": {"action": "spec_requested", "description": description},
                "handled": True,
                "artifact_id": None,
                "artifact_type": "agent_spec",
            }

        elif intent_type == "lookup":
            query = params.get("query", "").strip()
            # Search ideas first, then capabilities
            async with self._pool.connection() as db:
                ideas = parse_rows(
                    await db.query(
                        "SELECT title, raw_input, status, starred FROM idea WHERE product = <record>$product AND (title CONTAINS $q OR raw_input CONTAINS $q) LIMIT 3",
                        {"product": product_id, "q": query},
                    )
                )
            if ideas:
                items = "\n".join(
                    f"- **{i.get('title', '?')}** [{i.get('status', '?')}]: {i.get('raw_input', '')[:100]}"
                    for i in ideas
                )
                return {
                    "response": f"Found {len(ideas)} item(s) matching '{query}':\n{items}",
                    "data": {"ideas": ideas},
                    "handled": True,
                }
            # Try capability
            slug = query.replace(" ", "_").lower()
            cap = await self._product_map.get_capability(slug, product_id)
            if cap:
                return {
                    "response": f"**{cap.get('name', slug)}** ({cap.get('status', '?')})\n{cap.get('description', '')}",
                    "data": cap,
                    "handled": True,
                }
            # Nothing found — fall through to full orchestration which has
            # conversation context and can understand what the user meant.
            return {"response": "", "data": {}, "handled": False}

        elif intent_type == "list_ideas":
            async with self._pool.connection() as db:
                ideas = parse_rows(
                    await db.query(
                        "SELECT title, status, starred FROM idea WHERE product = <record>$product AND status NOT IN ['archived', 'completed'] ORDER BY starred DESC",
                        {"product": product_id},
                    )
                )
            if not ideas:
                return {"response": "Backlog is empty.", "data": {}, "handled": True}
            items = "\n".join(
                f"{'★' if i.get('starred') else '  '} [{i.get('status', '?'):10s}] {i.get('title', '?')}" for i in ideas
            )
            return {
                "response": f"Backlog ({len(ideas)} items):\n{items}",
                "data": {"ideas": ideas},
                "handled": True,
            }

        return {"response": "", "data": {}, "handled": False}
