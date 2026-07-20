"""Structured context blocks — compile intelligence into named prompt sections.

External agents (Claude Code, Cursor, etc.) get structured blocks instead of
flat insight lists. Each block has a role, content, token estimate, and freshness.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def compile_context_blocks(intelligence: dict, product_id: str) -> list[dict]:
    """Compile loaded intelligence into 6 named context blocks.

    Args:
        intelligence: Dict from load_dual_intelligence or load_intelligence,
            containing keys like 'insights', 'cross_domain', 'recent_signals', etc.
        product_id: Organization ID for context.

    Returns:
        List of context block dicts, each with: name, role, content, token_estimate,
        source_count, freshness.
    """
    blocks = []

    # Block 0 (highest priority): Graph Tensions — contradictions + consequences
    gt = intelligence.get("graph_tensions", {}) or {}
    tension_items = list(gt.get("tensions") or []) + list(gt.get("consequences") or [])
    if tension_items:
        lines = ["⚠ TENSIONS — These conflict with or have consequences for prior decisions — address them:"]
        for n in tension_items[:6]:
            rel = n.get("relationship", "")
            verb = {"breaks": "CONTRADICTS", "reverts": "REVERTS", "causes": "CAUSED"}.get(rel, rel.upper())
            lines.append(f"- ⚠ {verb}: {n.get('content', '')[:300]}")
        tension_content = "\n".join(lines)
        blocks.append(
            {
                "name": "graph_tensions",
                "role": "system",
                "content": tension_content,
                "token_estimate": _estimate_tokens(tension_content),
                "source_count": len(tension_items),
                "freshness": "current",
            }
        )

    # Block 1: Domain Expertise — top insights from specialty graph
    domain_insights = [i for i in intelligence.get("insights", []) if i.get("insight_type") != "correction"]
    blocks.append(
        _build_block(
            name="domain_expertise",
            role="system",
            items=domain_insights,
            header="What's true about this domain:",
            max_items=10,
        )
    )

    # Block 2: Org Conventions — preferences, procedures
    org_insights = [i for i in intelligence.get("insights", []) if i.get("insight_type") in ("preference", "procedure")]
    blocks.append(
        _build_block(
            name="org_conventions",
            role="system",
            items=org_insights,
            header="How we do things:",
            max_items=8,
        )
    )

    # Block 3: Recent Corrections
    corrections = [i for i in intelligence.get("insights", []) if i.get("insight_type") == "correction"]
    blocks.append(
        _build_block(
            name="recent_corrections",
            role="system",
            items=corrections,
            header="What we got wrong recently:",
            max_items=5,
        )
    )

    # Block 4: Active Context — recent signals and raw context
    signals = intelligence.get("recent_signals", [])
    blocks.append(
        _build_block(
            name="active_context",
            role="user",
            items=signals,
            header="Recent activity and signals:",
            max_items=5,
        )
    )

    # Block 5: Cross-Domain Connections
    cross = intelligence.get("cross_domain", [])
    blocks.append(
        _build_block(
            name="connections",
            role="system",
            items=cross,
            header="What adjacent domains say about this:",
            max_items=5,
        )
    )

    # Block 6: Calibration Notes
    calibration = intelligence.get("calibration_notes", [])
    if calibration:
        cal_content = "\n".join(f"- {note}" for note in calibration)
    else:
        cal_content = "No calibration concerns for this domain."
    blocks.append(
        {
            "name": "calibration_notes",
            "role": "system",
            "content": f"Where to be careful:\n{cal_content}",
            "token_estimate": _estimate_tokens(cal_content),
            "source_count": len(calibration),
            "freshness": "current",
        }
    )

    # Filter empties; tensions block (if any) leads — the partner/LLM confronts contradictions first.
    kept = [b for b in blocks if b["source_count"] > 0 or b["name"] == "calibration_notes"]
    kept.sort(key=lambda b: 0 if b["name"] == "graph_tensions" else 1)
    return kept


def _build_block(
    name: str,
    role: str,
    items: list[dict],
    header: str,
    max_items: int = 10,
) -> dict:
    """Build a single context block from a list of items."""
    selected = sorted(
        items,
        key=lambda x: x.get("confidence", 0),
        reverse=True,
    )[:max_items]

    lines = [header]
    for item in selected:
        content = item.get("content", "")[:300]
        confidence = item.get("confidence", 0)
        lines.append(f"- [{confidence:.0%}] {content}")

    content = "\n".join(lines)
    freshness = _assess_freshness(selected)

    return {
        "name": name,
        "role": role,
        "content": content,
        "token_estimate": _estimate_tokens(content),
        "source_count": len(selected),
        "freshness": freshness,
    }


def _estimate_tokens(text: str) -> int:
    """Rough token estimate without tokenizer dependency."""
    return len(text) // 4


def _assess_freshness(items: list[dict]) -> str:
    """Assess freshness based on newest item's age."""
    if not items:
        return "stale"

    now = datetime.now(timezone.utc)
    newest = None
    for item in items:
        created = item.get("created_at") or item.get("last_confirmed")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        if isinstance(created, datetime):
            if newest is None or created > newest:
                newest = created

    if newest is None:
        return "stale"

    age = now - newest
    if age < timedelta(days=7):
        return "current"
    if age < timedelta(days=30):
        return "aging"
    return "stale"
