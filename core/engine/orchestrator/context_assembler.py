# engine/orchestrator/context_assembler.py
"""ContextAssembler — composable intelligence context builder.

Replaces the monolithic ``_build_intel_context`` / ``_build_graph_intel_context``
functions in executor.py with a class whose sections are independently
overridable and token-budget-aware.

Token budget:
    Sections are split into two groups:
    - Priority sections: processed in order, dropped when budget runs out.
    - Pinned sections: always rendered last, budget is reserved for them first.

    Token count is approximated at ~4 chars/token (good enough for budget
    allocation — we don't need exact counts here).

Section priority (highest → lowest):
    1. Specialty insights (established expert knowledge)
    2. Recent signals (unverified but fresh)
    3. Graph context (code-level intelligence)
    4. PM context (decisions, initiatives, gaps)
    5. Product map (capability list)
    6. Risk context (blast radius, seam violations)
    7. Legacy insights (backward-compat fallback)

Pinned last (recency bias — maximum model attention):
    - Failure memory (known failure patterns)
    - Org insights (team-specific conventions)
    - Graph tensions (contradictions/consequences — confronted last, budget-immune)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

# ~4 chars per token is a safe approximation for English prose + code paths
_CHARS_PER_TOKEN = 4

# Rendering cache — avoids re-rendering identical snapshots during bursts.
# Keyed by (snapshot_hash, max_tokens) → (rendered_text, cached_at_epoch).
_RENDER_CACHE_TTL = 60  # seconds
_RENDER_CACHE_MAX = 64
_render_cache: dict[tuple[str, int], tuple[str, float]] = {}


def _snapshot_hash(snapshot: dict) -> str:
    """Deterministic content hash for snapshot dicts.

    Uses sort_keys + default=str so RecordIDs, datetimes, and other non-JSON
    types still round-trip without raising — rendering is a pure function of
    the visible content, so string coercion is the right equivalence.
    """
    try:
        blob = json.dumps(snapshot, sort_keys=True, default=str)
    except Exception:
        # Unhashable content → no cache entry, but render still proceeds.
        return ""
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _cache_get(key: tuple[str, int]) -> str | None:
    entry = _render_cache.get(key)
    if entry is None:
        return None
    text, cached_at = entry
    if time.time() - cached_at > _RENDER_CACHE_TTL:
        _render_cache.pop(key, None)
        return None
    return text


def _cache_set(key: tuple[str, int], text: str) -> None:
    if not key[0]:  # empty hash → unhashable snapshot, don't cache
        return
    # Simple size cap: evict an arbitrary oldest entry when full.
    if len(_render_cache) >= _RENDER_CACHE_MAX:
        try:
            oldest_key = min(_render_cache, key=lambda k: _render_cache[k][1])
            _render_cache.pop(oldest_key, None)
        except ValueError:
            pass
    _render_cache[key] = (text, time.time())


_EXT_TO_LANG = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".surql": "sql",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
}


class ContextAssembler:
    """Build a structured intelligence context string from a loader snapshot.

    Usage::

        assembler = ContextAssembler(max_tokens=4000)
        context = assembler.build(snapshot)

    Each section is a separate method so callers can subclass and override
    individual sections without touching the assembly loop.
    """

    # Sections processed in budget-priority order.
    # Earlier sections get space first; later sections are dropped when budget runs out.
    _PRIORITY_ORDER = [
        "star_traces",  # proven reasoning patterns — highest priority, loads first
        "specialty_insights",
        "recent_signals",
        "graph_context",
        "code_context",  # actual file content for matched files
        "pm_context",
        "decisions",  # recent architectural choices (fallback when pm_context absent)
        "arch_decisions",  # cross-session architectural memory (architecture + trade_off, no discipline filter)
        "cost_estimate",  # pre-task cost prediction from token ledger history
        "product_map",
        "risk_context",
        "legacy_insights",
    ]

    # Sections always rendered LAST regardless of budget.
    # Exploits recency bias: models attend most to end of context.
    _PINNED_LAST = [
        "failure_memory",  # renders before conventions — failure modes
        "org_insights",  # team-specific conventions
        "graph_tensions",  # renders LAST (maximum recency) — confront contradictions right before reasoning; budget-immune
    ]

    _SECTION_ORDER = _PRIORITY_ORDER  # backward compat alias

    def __init__(self, max_tokens: int = 6000) -> None:
        self.max_tokens = max_tokens
        self._max_chars = max_tokens * _CHARS_PER_TOKEN
        self._use_markers = False
        self._marker_idx = 0
        self._markers: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def build_with_markers(self, snapshot: dict) -> tuple[str, dict[str, str]]:
        """Build context string with [I-N] markers prepended to each insight.

        Returns (context_str, marker_map) where marker_map maps "[I-N]" -> insight_id.
        """
        self._markers = {}
        self._marker_idx = 0
        self._use_markers = True
        try:
            context = self.build(snapshot)
        finally:
            self._use_markers = False
        return context, self._markers

    def build(self, snapshot: dict) -> str:
        """Build context string with pinned-last rendering for recency bias.

        1. Build pinned sections first — reserve their budget
        2. Fill remaining budget with priority sections
        3. Render: priority sections first, pinned sections last

        When not collecting markers (the common path), cached renderings are
        served for identical (snapshot, max_tokens) pairs seen within the TTL.
        The marker path always renders fresh because it has side-effects.
        """
        # Marker path: no cache — build_with_markers has side-effects.
        # The plain build path is pure over snapshot + max_tokens and caches.
        cacheable = not getattr(self, "_use_markers", False)
        cache_key: tuple[str, int] | None = None
        if cacheable:
            cache_key = (_snapshot_hash(snapshot), self._max_chars)
            cached = _cache_get(cache_key)
            if cached is not None:
                return cached

        # Step 1: Build pinned sections and measure their budget cost.
        # Pinned sections are always included in full — their budget is reserved
        # before priority sections are allocated. Cap at half the total budget to
        # prevent monopolising when the budget is generous, but never truncate to
        # the point of losing content (prefer dropping priority sections instead).
        pinned_parts: list[str] = []
        pinned_chars = 0
        for key in self._PINNED_LAST:
            method = getattr(self, f"_section_{key}", None)
            if method is None:
                continue
            text = method(snapshot)
            if text:
                pinned_parts.append(text)
                pinned_chars += len(text)

        # Step 2: Fill remaining budget with priority sections.
        # Pinned sections are always included first, so the available budget for
        # priority sections is what remains. When pinned sections already exceed
        # the total budget (very low max_tokens), skip truncation for priority
        # sections — it is better to exceed the budget than to silently drop the
        # highest-priority content.
        remaining_after_pinned = self._max_chars - pinned_chars
        in_overflow = remaining_after_pinned <= 0
        available = self._max_chars if in_overflow else remaining_after_pinned
        parts: list[str] = []
        used_chars = 0

        for section_key in self._PRIORITY_ORDER:
            if not in_overflow and used_chars >= available:
                logger.debug(
                    "ContextAssembler: budget exhausted at section=%s used_tokens≈%d",
                    section_key,
                    used_chars // _CHARS_PER_TOKEN,
                )
                break
            method = getattr(self, f"_section_{section_key}", None)
            if method is None:
                continue
            text = method(snapshot)
            if not text:
                continue
            if not in_overflow:
                remaining = available - used_chars
                if len(text) > remaining:
                    text = self._truncate_at_newline(text, remaining)
                    if not text:
                        break
            parts.append(text)
            used_chars += len(text)

        # Step 3: Pinned sections go last (recency bias — maximum model attention)
        result = "".join(parts) + "".join(pinned_parts)
        if cacheable and cache_key is not None:
            _cache_set(cache_key, result)
        return result

    # ------------------------------------------------------------------ #
    # Sections (override any of these in a subclass)                      #
    # ------------------------------------------------------------------ #

    def _section_specialty_insights(self, snapshot: dict) -> str:
        items = snapshot.get("specialty_insights", [])
        if not items:
            return ""
        lines = ["\n\n## Expert Knowledge\nThe following is established knowledge from your specialties:"]
        for ins in items[:20]:
            if self._use_markers:
                self._marker_idx += 1
                marker = f"[I-{self._marker_idx}]"
                ins_id = str(ins.get("id", ""))
                if ins_id:
                    self._markers[marker] = ins_id
                lines.append(f"- {marker} [{ins.get('confidence', 0):.2f}] {ins.get('content', '')}")
            else:
                lines.append(f"- [{ins.get('confidence', 0):.2f}] {ins.get('content', '')}")
        return "\n".join(lines)

    def _section_star_traces(self, snapshot: dict) -> str:
        """Render star traces as 'Proven Reasoning Patterns' section."""
        star_traces = snapshot.get("star_traces", [])
        if not star_traces:
            return ""
        lines = ["## Proven Reasoning Patterns\n"]
        lines.append("These are successful reasoning approaches for similar tasks:\n")
        for i, trace in enumerate(star_traces, 1):
            desc = trace.get("task_description", "")
            output = trace.get("final_output", "")
            lines.append(f"**Example {i}:** {desc}")
            if output:
                lines.append(f"Outcome: {output}")
            lines.append("")
        return "\n".join(lines)

    def _section_failure_memory(self, snapshot: dict) -> str:
        """Render aggregated failure patterns from similar past tasks."""
        entries = snapshot.get("failure_memory", [])
        if not entries:
            return ""

        lines = [
            "\n## Known Failure Patterns (from similar past tasks)\n"
            "These gaps recurred in previous similar tasks — verify they are addressed:\n"
        ]
        for entry in entries[:7]:
            if "pattern" in entry:
                # Aggregated format: {"pattern": str, "count": int}
                count = entry.get("count", 1)
                count_str = f" ×{count}" if count > 1 else ""
                lines.append(f"  - {entry['pattern']}{count_str}")
            else:
                # Legacy raw format: {"gaps": [...]}
                for gap in entry.get("gaps", []):
                    lines.append(f"  - {gap}")
        return "\n".join(lines)

    def _section_org_insights(self, snapshot: dict) -> str:
        items = snapshot.get("org_insights", [])
        if not items:
            return ""
        lines = ["\n## Team Context\nThe following is specific to this organization:"]
        for ins in items[:15]:
            if self._use_markers:
                self._marker_idx += 1
                marker = f"[I-{self._marker_idx}]"
                ins_id = str(ins.get("id", ""))
                if ins_id:
                    self._markers[marker] = ins_id
                lines.append(f"- {marker} [{ins.get('confidence', 0):.2f}] {ins.get('content', '')}")
            else:
                lines.append(f"- [{ins.get('confidence', 0):.2f}] {ins.get('content', '')}")
        return "\n".join(lines)

    def _section_graph_tensions(self, snapshot: dict) -> str:
        gt = snapshot.get("graph_tensions", {}) or {}
        items = list(gt.get("tensions") or []) + list(gt.get("consequences") or [])
        if not items:
            return ""
        lines = [
            "\n\n## ⚠ Tensions\nThese conflict with or have consequences for prior decisions — address them directly:"
        ]
        for n in items[:6]:
            rel = n.get("relationship", "")
            verb = {"breaks": "CONTRADICTS", "reverts": "REVERTS", "causes": "CAUSED"}.get(rel, rel.upper())
            lines.append(f"- ⚠ {verb}: {n.get('content', '')[:300]}")
        return "\n".join(lines)

    def _section_recent_signals(self, snapshot: dict) -> str:
        items = snapshot.get("recent_signals", [])
        if not items:
            return ""
        lines = [
            "\n\n## Recent Observations (unverified)\n"
            "These signals were captured recently from related work. Treat with appropriate skepticism:"
        ]
        for s in items[:10]:
            lines.append(
                f"- [{s.get('observation_type', '?')}] {s.get('content', '')} (confidence: {s.get('confidence', '?')})"
            )
        return "\n".join(lines)

    def _section_graph_context(self, snapshot: dict) -> str:
        graph_context = snapshot.get("graph_context")
        if not graph_context:
            return ""
        return _build_graph_section(graph_context)

    def _section_code_context(self, snapshot: dict) -> str:
        """Render actual file content for files matched to this task."""
        ctx = snapshot.get("code_context")
        if not ctx or not ctx.get("files"):
            return ""
        lines = ["\n\n## Relevant Code (matched to this task)"]
        for f in ctx["files"][:4]:
            path = f.get("path", "")
            content = f.get("content", "").strip()
            reason = f.get("reason", "")
            if not content:
                continue
            content_lines = content.splitlines()
            if len(content_lines) > 60:
                content = "\n".join(content_lines[:60]) + "\n... (truncated)"
            ext = os.path.splitext(path)[1].lower()
            lang = _EXT_TO_LANG.get(ext, "")
            reason_str = f"  # {reason}" if reason else ""
            lines.append(f"\n### {path}{reason_str}\n```{lang}\n{content}\n```")
        return "\n".join(lines) if len(lines) > 1 else ""

    def _section_pm_context(self, snapshot: dict) -> str:
        pm = snapshot.get("pm_context")
        if not pm:
            return ""
        parts: list[str] = []

        decisions = pm.get("decisions", [])
        if decisions:
            parts.append("\n## Recent Decisions")
            for d in decisions[:5]:
                outcome = d.get("outcome", "?")
                title = d.get("title", "untitled")
                dtype = d.get("decision_type", "")
                parts.append(f"- [{dtype}] {title} → {outcome}")

        inits = pm.get("initiatives", [])
        if inits:
            parts.append("\n## Active Initiatives")
            for i in inits[:5]:
                status = i.get("status", "?")
                title = i.get("title", "untitled")
                budget_str = ""
                if i.get("cost_budget"):
                    used = i.get("cost_used", 0) or 0
                    total = i.get("cost_budget", 0)
                    budget_str = f" (${used:.0f}/${total:.0f})"
                parts.append(f"- {title} [{status}]{budget_str}")

        gaps = pm.get("quality_gaps", [])
        if gaps:
            parts.append("\n## Quality Gaps (score < 50%)")
            for g in gaps[:5]:
                cap = g.get("capability", "?")
                dim = g.get("dimension", "?")
                score = g.get("score", 0)
                parts.append(f"- {cap}/{dim}: {score:.0%}")

        agent_count = pm.get("live_agents", 0)
        if agent_count:
            parts.append(f"\n## Live: {agent_count} agent(s) currently executing")

        return "\n".join(parts)

    def _section_decisions(self, snapshot: dict) -> str:
        """Render recent decisions — suppressed when pm_context already has decisions."""
        # Avoid duplication: _section_pm_context renders "Recent Decisions"
        # from the same underlying table. Only render here as a fallback.
        pm = snapshot.get("pm_context") or {}
        if pm.get("decisions"):
            return ""

        items = snapshot.get("decisions", [])
        if not items:
            return ""

        lines = ["\n\n## Prior Decisions (recent architectural choices)"]
        for d in items[:5]:
            title = d.get("title", "untitled")
            dtype = d.get("decision_type", "")
            outcome = d.get("outcome") or "pending"
            rationale = d.get("rationale", "")
            rationale_str = f" — {rationale[:80]}" if rationale else ""
            lines.append(f"- [{dtype}] {title} → {outcome}{rationale_str}")
        return "\n".join(lines)

    def _section_arch_decisions(self, snapshot: dict) -> str:
        """Cross-session architectural memory — architecture + trade_off decisions, all disciplines."""
        items = snapshot.get("arch_decisions", [])
        if not items:
            return ""
        lines = ["\n\n## Architectural Memory (cross-session)"]
        for d in items[:8]:
            title = d.get("title", "untitled")
            dtype = d.get("decision_type", "")
            outcome = d.get("outcome") or "pending"
            rationale = d.get("rationale", "")
            hint = d.get("discipline_hint", "")
            domain = f" [{hint}]" if hint else ""
            rationale_str = f" — {rationale[:100]}" if rationale else ""
            lines.append(f"- [{dtype}]{domain} {title} → {outcome}{rationale_str}")
        return "\n".join(lines)

    def _section_cost_estimate(self, snapshot: dict) -> str:
        """Pre-task cost estimate from token ledger history."""
        est = snapshot.get("cost_estimate")
        if not est or est.get("sample_count", 0) == 0:
            return ""
        p50 = est.get("p50_usd", 0)
        p90 = est.get("p90_usd", 0)
        n = est.get("sample_count", 0)
        discipline = est.get("discipline", "")
        return f"\n\n## Cost Estimate\nBased on {n} past {discipline} tasks: p50 ${p50:.4f} · p90 ${p90:.4f} per task."

    def _section_product_map(self, snapshot: dict) -> str:
        product = snapshot.get("product_context")
        if not product or not product.get("capabilities"):
            return ""
        lines = ["\n\n## Product Map", f"Total capabilities: {product['total_capabilities']}"]
        for cap in product["capabilities"]:
            status = cap.get("status", "unknown")
            name = cap.get("name") or cap.get("slug", "?")
            desc = f" — {cap['description']}" if cap.get("description") else ""
            lines.append(f"- {name} ({status}){desc}")
        return "\n".join(lines)

    def _section_risk_context(self, snapshot: dict) -> str:
        risk = snapshot.get("risk_context")
        if not risk:
            return ""
        parts: list[str] = []

        blast = risk.get("blast_radius", [])
        if blast:
            total_matched = blast[0].get("total_matched", len(blast))
            parts.append(f"\n\n## Blast Radius ({total_matched} files touched, top {len(blast)} shown)")
            for br in blast:
                parts.append(f"- {br['file']}: {br['direct']} direct, {br['total']} total affected")

        seam_gaps = risk.get("seam_gaps", [])
        if seam_gaps:
            parts.append("\n\n## Seam Violations (existing API contract mismatches)")
            for gap in seam_gaps[:5]:
                sev = gap.get("severity", "?").upper()
                route = gap.get("route", "?")
                method = gap.get("method", "?")
                desc = gap.get("description", "")
                parts.append(f"- [{sev}] {method} {route}: {desc}")

        return "".join(parts)

    def _section_legacy_insights(self, snapshot: dict) -> str:
        """Fallback: legacy single-list format from pre-dual-graph loader."""
        # Only emit when neither specialty nor org insights are present
        if snapshot.get("specialty_insights") or snapshot.get("org_insights"):
            return ""
        items = snapshot.get("insights", [])
        if not items:
            return ""
        lines = ["\n\n## Established Intelligence\nThese are validated insights at this domain path:"]
        for i in items:
            if self._use_markers:
                self._marker_idx += 1
                marker = f"[I-{self._marker_idx}]"
                insight_id = str(i.get("id", ""))
                if insight_id:
                    self._markers[marker] = insight_id
                lines.append(f"- {marker} [{i['insight_type']}] {i['content']} (confidence: {i['confidence']})")
            else:
                lines.append(f"- [{i['insight_type']}] {i['content']} (confidence: {i['confidence']})")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _truncate_at_newline(text: str, max_chars: int) -> str:
        """Truncate *text* to at most *max_chars*, ending at a newline boundary."""
        if len(text) <= max_chars:
            return text
        cut = text.rfind("\n", 0, max_chars)
        if cut <= 0:
            return ""  # Can't fit even one line — skip entirely
        return text[:cut]


# ------------------------------------------------------------------ #
# Graph section helper (used by _section_graph_context above)         #
# ------------------------------------------------------------------ #


def _build_graph_section(graph_context: dict) -> str:
    """Build prompt context from graph intelligence data."""
    sections: list[str] = []

    relevant_files = graph_context.get("relevant_files", [])
    if relevant_files:
        sections.append("\n\n## Code Context (from intelligence graph)")
        for f in relevant_files[:10]:
            parts = [f["path"]]
            fc = f.get("function_count", 0)
            dc = f.get("dependent_count", 0)
            if fc:
                parts.append(f"{fc} functions")
            if dc:
                parts.append(f"{dc} dependents")
            sections.append(f"- {', '.join(parts)}")

    decisions = graph_context.get("decisions", [])
    if decisions:
        sections.append("\n## Decision History")
        for d in decisions[:5]:
            desc = d.get("description", "")[:100]
            sections.append(f"- {d['title']}: {desc}")

    risk_flags = graph_context.get("risk_flags", [])
    if risk_flags:
        sections.append("\n## Risk Flags")
        for r in risk_flags:
            sections.append(f"- {r}")

    dependencies = graph_context.get("dependencies", [])
    if dependencies:
        sections.append("\n## Key Dependencies")
        seen: set[str] = set()
        for dep in dependencies[:8]:
            path = dep.get("to_path") or dep.get("from_path", "")
            dtype = dep.get("type", "")
            key = f"{path}:{dtype}"
            if key not in seen and path:
                seen.add(key)
                sections.append(f"- {path} ({dtype})")

    return "\n".join(sections) if sections else ""


# Module-level default instance — callers can import and use directly
context_assembler = ContextAssembler()
