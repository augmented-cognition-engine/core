# engine/mcp/server.py
"""ACE MCP server — exposes tools for Claude Code, Cursor, and MCP-compatible hosts.

Run: ace-mcp (or: python -m engine.mcp.server)
"""

from __future__ import annotations

from fastmcp import FastMCP

DEFAULT_PRODUCT = "product:platform"

mcp = FastMCP(
    "ACE Intelligence Engine",
    instructions="Intelligence that compounds. Load knowledge, capture observations, run tasks through ACE's full orchestrator.",
)


_CAPTURE_ICONS = {
    "decision": "🔷",
    "correction": "🔴",
    "pattern": "🔶",
    "preference": "🟡",
    "learning": "🟢",
    "error": "❌",
    "question": "❓",
}
_SEP = "─" * 46

_SEVERITY_ICONS = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "○",
}


def _fmt_impact(d: dict, file_path: str) -> str:
    safe = d.get("safe_to_delete", True)
    indicator = "✓ SAFE" if safe else "⚠ BREAKING"
    importers = d.get("importers", [])
    caps = d.get("capabilities", [])
    fns = d.get("functions_defined", [])
    label = file_path.split("/")[-1]
    lines = [f"{'✓' if safe else '⚠'} Impact  ·  {label}  ·  {indicator}", _SEP]
    lines.append(f"{len(importers)} importers  ·  {len(fns)} functions  ·  {len(caps)} capabilities")
    if importers:
        lines.append("")
        lines.append("Importers:")
        for imp in importers[:8]:
            lines.append(f"  {imp}")
        if len(importers) > 8:
            lines.append(f"  … +{len(importers) - 8} more")
    if caps:
        lines.append("")
        lines.append("Capabilities affected: " + ", ".join(caps[:6]))
    if not safe:
        lines.append("")
        lines.append("⚠  Breaking changes — review importers before proceeding.")
    return "\n".join(lines)


def _fmt_explain_gap(d: dict, capability_slug: str, dimension: str) -> str:
    score = float(d.get("score") or 0)
    conf = float(d.get("confidence") or 0)
    priority = d.get("priority", "medium")
    icon = "🔴" if priority == "high" else ("🟡" if priority == "medium" else "🟢")
    gaps = d.get("gaps", [])
    evidence = d.get("evidence", [])
    filled = round(score * 8)
    bar = "█" * filled + "░" * (8 - filled)
    lines = [f"{icon} Gap  ·  {capability_slug}  ×  {dimension}  ·  {bar} {score:.2f}  [conf: {conf:.2f}]", _SEP]
    if gaps:
        lines.append("Gaps:")
        for g in gaps:
            lines.append(f"  · {g}")
    if evidence:
        lines.append("")
        lines.append("Evidence checked:")
        for e in evidence[:5]:
            lines.append(f"  {e}")
    return "\n".join(lines)


def _fmt_diff_impact(d: dict) -> str:
    net = d.get("net_impact", "neutral")
    icon = {"positive": "✓", "negative": "⚠", "critical": "🔴", "neutral": "○"}.get(net, "○")
    preds = d.get("predictions", [])
    rec = d.get("recommendation", "")
    lines = [f"{icon} Diff Impact  ·  NET: {net.upper()}", _SEP]
    if rec:
        lines.append(rec)
    if preds:
        lines.append("")
        for p in preds:
            cap = p.get("capability", "?")
            dim = p.get("dimension", "?")
            delta = p.get("score_delta", 0)
            sign = "+" if delta >= 0 else ""
            lines.append(f"  {cap}  ·  {dim}  →  {sign}{delta:.2f}")
    return "\n".join(lines)


def _fmt_findings(d: dict) -> str:
    items = d.get("findings", [])
    total = d.get("total", len(items))
    lines = [f"◉ Findings  ·  {total} total", _SEP]
    by_sev: dict[str, list] = {}
    for f in items:
        sev = f.get("severity", "info")
        by_sev.setdefault(sev, []).append(f)
    for sev in ("critical", "high", "medium", "low", "info"):
        group = by_sev.get(sev, [])
        if not group:
            continue
        icon = _SEVERITY_ICONS.get(sev, "○")
        lines.append(f"\n{icon} {sev.upper()} ({len(group)})")
        for f in group[:5]:
            rule = f.get("rule_id", f.get("check", "?"))
            path = f.get("file_path", "")
            line = f.get("line", "")
            loc = f"{path}:{line}" if path and line else path or ""
            lines.append(f"  {rule}  {loc}")
        if len(group) > 5:
            lines.append(f"  … +{len(group) - 5} more")
    if not items:
        lines.append("No findings — clean scan.")
    return "\n".join(lines)


def _fmt_gates(items: list) -> str:
    lines = [f"⏳ Pending Gates  ·  {len(items)}", _SEP]
    if not items:
        lines.append("No pending gates.")
        return "\n".join(lines)
    for g in items:
        etype = g.get("entity_type", "?")
        eid = g.get("entity_id", g.get("id", "?"))
        title = g.get("title", eid)
        lines.append(f"  [{etype}]  {title}  ({eid})")
    lines.append("")
    lines.append("Run ace_approve_gate or ace_reject_gate to action each.")
    return "\n".join(lines)


@mcp.tool(title="Start")
async def ace_start(product_id: str = DEFAULT_PRODUCT) -> str:
    """Pre-flight check. Returns session context: briefing availability, active initiatives, ideas ready for review. Call this at the start of every session."""
    from core.engine.mcp.tools import ace_start as _start

    d = await _start(product_id=product_id)
    lines = [f"◈ ACE session started  ·  {product_id}", _SEP]
    if d.get("briefing_available"):
        date = str(d.get("last_briefing_date", ""))[:10]
        lines.append(f"✓ Briefing available ({date})")
    else:
        lines.append("○ No briefing yet")
    n = d.get("active_initiatives", 0)
    lines.append(f"{'✓' if n else '○'} {n} active initiative{'s' if n != 1 else ''}")
    ideas = d.get("ideas_ready", 0)
    if ideas:
        lines.append(f"💡 {ideas} idea{'s' if ideas != 1 else ''} ready for review")
    approvals = d.get("pending_approvals", 0)
    if approvals:
        lines.append(f"⚠ {approvals} pending approval{'s' if approvals != 1 else ''}")
    return "\n".join(lines)


@mcp.tool(title="Load")
async def ace_load(topic: str, product_id: str = DEFAULT_PRODUCT) -> str:
    """Load accumulated intelligence for a domain topic. Returns insights, corrections, preferences, and framework recommendation. Always call this before starting work in a domain. Do not attempt to help without loading organizational intelligence first."""
    from core.engine.mcp.tools import ace_load as _load

    d = await _load(topic=topic, product_id=product_id)
    total = d.get("total_count", 0)
    corrections = d.get("corrections", [])
    preferences = d.get("preferences", [])
    general = d.get("insights", [])

    lines = [f"◉ Intelligence loaded  ·  {d.get('domain_path', topic)}  ·  {total} insights", _SEP]

    _SHOW = 5  # progressive disclosure — top N per type

    if corrections:
        lines.append(f"🔴 Corrections ({len(corrections)})")
        for c in corrections[:_SHOW]:
            lines.append(f"  • {c.get('content', '')[:120]}")
        if len(corrections) > _SHOW:
            lines.append(f"  … +{len(corrections) - _SHOW} more  (ace_search to find specific ones)")

    if preferences:
        lines.append(f"🟡 Preferences ({len(preferences)})")
        for p in preferences[:_SHOW]:
            lines.append(f"  • {p.get('content', '')[:120]}")
        if len(preferences) > _SHOW:
            lines.append(f"  … +{len(preferences) - _SHOW} more")

    if general:
        lines.append(f"🔶 Insights ({len(general)})")
        for i in general[:_SHOW]:
            lines.append(f"  • {i.get('content', '')[:120]}")
        if len(general) > _SHOW:
            lines.append(f"  … +{len(general) - _SHOW} more  (ace_search to find specific ones)")

    if not total:
        lines.append("No intelligence captured yet for this domain.")

    return "\n".join(lines)


@mcp.tool(title="Capture")
async def ace_capture(
    observation_type: str,
    content: str,
    domain_path: str,
    confidence: float = 0.7,
) -> str:
    """Record an observation from this session. Types: correction, decision, preference, pattern, learning, error. Call when user corrects output ("that's wrong", "use X not Y"), makes a decision, states a preference, or when you discover a useful fact. ACE processes these into durable intelligence."""
    from core.engine.mcp.tools import ace_capture as _capture

    d = await _capture(
        observation_type=observation_type,
        content=content,
        domain_path=domain_path,
        confidence=confidence,
    )
    icon = _CAPTURE_ICONS.get(observation_type, "◆")
    obs_id = d.get("id", "")
    lines = [
        f"{icon} {observation_type.capitalize()} captured  ·  {domain_path}  ·  ↑{confidence}",
        _SEP,
        content[:200],
        f"→ {obs_id}",
    ]
    return "\n".join(lines)


@mcp.tool(title="Task")
async def ace_task(
    description: str,
    product_id: str = DEFAULT_PRODUCT,
    skill_hint: str | None = None,
    frameworks_hint: str | None = None,
) -> dict:
    """Run a task through ACE's full orchestrator: classify, load intelligence, select skill/frameworks, execute, capture learnings. Returns the intelligence-enriched result."""
    from core.engine.mcp.tools import ace_task as _task

    fw_list = frameworks_hint.split(",") if frameworks_hint else None
    return await _task(description=description, product_id=product_id, skill_hint=skill_hint, frameworks_hint=fw_list)


@mcp.tool(title="Agent")
async def ace_agent(
    description: str,
    product_id: str = DEFAULT_PRODUCT,
    model: str | None = None,
    max_turns: int = 50,
) -> dict:
    """Run an agentic implementation task through ACE Runtime. Full tool-use loop (bash, read, write, edit, grep, glob) grounded with ACE intelligence: discipline instructions, archetype, mode, cognitive composition phases, and loaded insights from the graph. Use for implementation work requiring multiple tool calls. Use ace_task for analytical/text output work."""
    from core.engine.mcp.tools import ace_agent as _agent

    return await _agent(description=description, product_id=product_id, model=model, max_turns=max_turns)


@mcp.tool(title="Status")
async def ace_status(product_id: str = DEFAULT_PRODUCT, filter: str | None = None) -> str:
    """Check autonomous work status: running initiatives, ideas ready for review, items needing approval."""
    from core.engine.mcp.tools import ace_status as _status

    data = await _status(product_id=product_id, filter=filter)

    lines = ["## ACE Status"]
    initiatives = data.get("initiatives", [])
    if initiatives:
        lines.append(f"\n**Active ({len(initiatives)})**")
        for i in initiatives:
            name = i.get("title") or i.get("name") or i.get("id", "—")
            dim = i.get("discipline") or i.get("dimension") or ""
            status = i.get("status", "")
            suffix = " — BLOCKED" if status == "blocked" else ""
            dim_part = f" · {dim}" if dim else ""
            lines.append(f"- {name}{dim_part}{suffix}")
    else:
        lines.append("\nNo active initiatives.")

    ideas = data.get("ideas_ready", 0)
    approvals = data.get("pending_approvals", 0)
    lines.append(f"\n**Ideas ready for review:** {ideas}")
    if approvals:
        lines.append(f"**Pending approvals:** {approvals}")

    return "\n".join(lines)


@mcp.tool(title="Rederive")
async def ace_rederive(product_id: str = DEFAULT_PRODUCT, limit: int = 5) -> str:
    """Re-evaluate beliefs whose canvas ground shifted — propose corrected confidences from the changed evidence (SHADOW: proposed, not applied)."""
    from core.engine.mcp.tools import ace_rederive as _rederive

    data = await _rederive(product_id=product_id, limit=limit)
    lines = [f"## Re-derivation — {data['rederived']} belief(s) re-evaluated (shadow, not applied)"]
    proposed = [b for b in data.get("destabilized_beliefs", []) if b.get("proposed_confidence") is not None]
    if not proposed:
        lines.append("\nNo destabilized beliefs with proposals yet.")
    for b in proposed:
        supp = "still supported" if b.get("still_supported") else "no longer supported"
        content = (b.get("belief_content") or "")[:80]
        lines.append(f"- {content} → proposed confidence {b['proposed_confidence']} ({supp})")
        rationale = b.get("rederivation_rationale")
        if rationale:
            lines.append(f"    ↳ {rationale}")
    return "\n".join(lines)


@mcp.tool(title="Capture Idea")
async def ace_capture_idea(raw_idea: str, context: str | None = None) -> str:
    """Drop an idea into ACE's incubator. Call when user says 'what if...', 'I want to explore...', 'remind me to think about...'. ACE will enrich it overnight: generate brief, find connections, identify gaps, qualify feasibility."""
    from core.engine.mcp.tools import ace_capture_idea as _capture_idea

    d = await _capture_idea(raw_idea=raw_idea, context=context)
    idea_id = d.get("id", d.get("idea_id", ""))
    lines = [
        "💡 Idea queued  ·  incubating overnight",
        _SEP,
        raw_idea[:200],
        "ACE will brief, connect, and score feasibility.",
    ]
    if idea_id:
        lines.append(f"→ {idea_id}")
    return "\n".join(lines)


@mcp.tool(title="Search")
async def ace_search(
    query: str,
    knowledge_type: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Search the intelligence graph with hybrid BM25 + vector (RRF).

    knowledge_type: optional filter — "pattern", "decision", "correction", "preference"
    tags: optional discipline/specialty filter — e.g. ["architecture", "error_handling"]
    """
    from core.engine.mcp.tools import ace_search as _search

    d = await _search(query=query, knowledge_type=knowledge_type, tags=tags)
    results = d.get("results", d.get("insights", []))
    filter_parts = []
    if knowledge_type:
        filter_parts.append(knowledge_type)
    if tags:
        filter_parts.append("tags:" + "+".join(tags))
    filter_label = ("  ·  " + "  ·  ".join(filter_parts)) if filter_parts else ""
    lines = [f'◎ Search: "{query}"{filter_label}  ·  {len(results)} results', _SEP]
    for r in results[:10]:
        itype = r.get("insight_type") or r.get("observation_type") or "insight"
        icon = _CAPTURE_ICONS.get(itype, "◆")
        rtags = r.get("tags", [])
        tag_str = f"  [{', '.join(rtags[:3])}]" if rtags else ""
        lines.append(f"{icon} [{itype}]{tag_str} {r.get('content', '')[:110]}")
    if len(results) > 10:
        lines.append(f"  … +{len(results) - 10} more")
    if not results:
        lines.append("No results found.")
    return "\n".join(lines)


@mcp.tool(title="Briefing")
async def ace_briefing(date: str | None = None, briefing_id: str | None = None) -> str:
    """Retrieve the intelligence briefing. Defaults to latest. Pass briefing_id for a specific version, date (YYYY-MM-DD) for a day. Shows what ACE learned, what needs attention, ideas ready."""
    from core.engine.mcp.tools import ace_briefing as _briefing

    data = await _briefing(date=date, briefing_id=briefing_id)

    if not data.get("available"):
        return "No briefing available yet. Run the conductor to generate one."

    parts = [data.get("content", "").strip()]

    pm = data.get("pm_central", {})

    whitespace = pm.get("whitespace", [])
    if whitespace:
        parts.append("\n## Whitespace Opportunities")
        for w in whitespace:
            score = f"{w.get('whitespace_score', 0):.2f}"
            parts.append(f"- {w.get('title', w.get('slug', '?'))} (score: {score})")

    health = pm.get("product_health", [])
    if health:
        parts.append("\n## Weakest Dimensions")
        for h in health:
            dim = h.get("dimension", "?")
            avg = h.get("avg_score", 0)
            gaps = h.get("gap_count", 0)
            parts.append(f"- {dim}: {avg:.2f} · {gaps} gaps")

    market = pm.get("market_moves", [])
    if market:
        parts.append("\n## Market Moves (last 24h)")
        for m in market:
            parts.append(f"- {m.get('competitor', '?')} — {m.get('summary', '')}")

    return "\n".join(parts)


@mcp.tool(title="Impact")
async def ace_impact(file_path: str, product_id: str = DEFAULT_PRODUCT) -> str:
    """What breaks if I delete or change this file? Returns importers, functions, capabilities affected. Use before deleting or refactoring."""
    from core.engine.mcp.tools import ace_impact as _impact

    d = await _impact(file_path=file_path, product_id=product_id)
    return _fmt_impact(d, file_path)


@mcp.tool(title="Impact Path")
async def ace_impact_path(file_path: str, product_id: str = DEFAULT_PRODUCT) -> str:
    """Alias for ace_impact — what breaks if I delete this file? Calls the graph impact-by-path analysis and returns importers, functions defined, and capabilities affected."""
    from core.engine.mcp.tools import ace_impact as _impact

    d = await _impact(file_path=file_path, product_id=product_id)
    return _fmt_impact(d, file_path)


@mcp.tool(title="History")
async def ace_history(file_path: str, graph_id: str = "default") -> str:
    """Why was this file built this way? Returns the decision trail — what decisions were made, what was tried, what succeeded. Call this when you encounter code that seems odd or over-engineered."""
    from core.engine.mcp.tools import ace_history as _history

    return await _history(file_path=file_path, graph_id=graph_id)


@mcp.tool(title="Related")
async def ace_related(file_path: str, graph_id: str = "default") -> str:
    """What's connected to this file? Returns imports (outgoing), importers (incoming), co-changed files, and related decisions — everything 1-2 hops away in the knowledge graph."""
    from core.engine.mcp.tools import ace_related as _related

    return await _related(file_path=file_path, graph_id=graph_id)


@mcp.tool(title="Health")
async def ace_product_health(
    product_id: str = DEFAULT_PRODUCT,
    explain: str | None = None,
) -> str:
    """Product health summary: capabilities, quality scores, gaps across all disciplines. D2: includes 30-day trend arrows per dimension. D4: set explain='security' to get per-capability gaps and evidence for that dimension."""
    from core.engine.mcp.tools import ace_product_health as _health

    d = await _health(product_id=product_id, explain=explain)

    def _bar(score: float) -> str:
        filled = round(score * 8)
        return "█" * filled + "░" * (8 - filled)

    dims = d.get("dimensions", {})
    total_caps = d.get("total_capabilities", len(dims))
    lines = [f"◉ Product Health  ·  {total_caps} capabilities", _SEP]

    for dim, data in sorted(dims.items(), key=lambda x: x[1].get("avg_score", 0)):
        score = float(data.get("avg_score") or 0)
        arrow = data.get("trend_arrow", "")
        gaps = data.get("gap_count", 0)
        gap_tag = f"  {gaps}g" if gaps else ""
        lines.append(f"{_bar(score)} {score:.2f} {arrow}  {dim}{gap_tag}")

    if explain:
        exp = d.get("explanation", {})
        caps = exp.get("capabilities", [])
        lines.append(f"\n── {explain} detail ──")
        for c in caps[:10]:
            slug = c.get("slug", "?")
            s = float(c.get("score") or 0)
            gs = c.get("gaps", [])
            lines.append(f"  {_bar(s)} {s:.2f}  {slug}")
            for g in gs[:2]:
                lines.append(f"    · {g[:100]}")

    return "\n".join(lines)


@mcp.tool(title="Gaps")
async def ace_gaps(product_id: str = DEFAULT_PRODUCT, dimension: str | None = None) -> str:
    """Current quality gaps where score < 0.6. Optionally filter by dimension (security, testing, etc). D5: includes confidence label per gap. D1: includes file:line findings from static analysis where available."""
    from core.engine.mcp.tools import ace_gaps as _gaps

    d = await _gaps(product_id=product_id, dimension=dimension)
    gaps = d.get("gaps", [])
    filter_label = f"  ·  {dimension}" if dimension else ""
    lines = [f"⚠ Gaps{filter_label}  ·  {len(gaps)} below threshold", _SEP]

    # Group by dimension
    by_dim: dict = {}
    for g in gaps:
        dim = g.get("dimension", "?")
        by_dim.setdefault(dim, []).append(g)

    for dim, items in sorted(by_dim.items(), key=lambda x: min(i.get("score", 1) for i in x[1])):
        lines.append(f"\n{dim}")
        for item in sorted(items, key=lambda x: x.get("score", 1))[:5]:
            cap_id = str(item.get("capability", ""))
            slug = cap_id.split(":")[-1] if ":" in cap_id else cap_id
            score = float(item.get("score") or 0)
            conf = item.get("confidence_label", "")
            conf_tag = f"  [{conf}]" if conf else ""
            lines.append(f"  {score:.2f}{conf_tag}  {slug}")
            for gap_text in (item.get("gaps") or [])[:2]:
                lines.append(f"    · {str(gap_text)[:100]}")
            findings = item.get("findings", [])
            for f in findings[:1]:
                lines.append(f"    ↳ {f.get('file', '?')}:{f.get('line', '?')}  {f.get('message', '')[:80]}")
        if len(items) > 5:
            lines.append(f"  … +{len(items) - 5} more in {dim}")

    if not gaps:
        lines.append("No gaps — all capabilities above threshold.")

    return "\n".join(lines)


@mcp.tool(title="Explain Gap")
async def ace_explain_gap(
    capability_slug: str,
    dimension: str,
    product_id: str = DEFAULT_PRODUCT,
) -> str:
    """D4: Explain why a capability has a low score in a specific dimension. Returns specific gaps, evidence checked, confidence level, and fix priority. Example: ace_explain_gap('auth_system', 'security') → 'JWT secret hardcoded in config'."""
    from core.engine.mcp.tools import ace_explain_gap as _explain

    d = await _explain(capability_slug=capability_slug, dimension=dimension, product_id=product_id)
    return _fmt_explain_gap(d, capability_slug, dimension)


@mcp.tool(title="Diff Impact")
async def ace_diff_impact(diff: str, product_id: str = DEFAULT_PRODUCT) -> str:
    """D3: Predict how a code diff will change discipline scores. Pass git diff output before merging a PR. Identifies affected capabilities via realizes edges and predicts score changes. Returns net_impact: positive|negative|critical|neutral."""
    from core.engine.mcp.tools import ace_diff_impact as _diff

    d = await _diff(diff=diff, product_id=product_id)
    return _fmt_diff_impact(d)


@mcp.tool(title="Recommend")
async def ace_recommend(product_id: str = DEFAULT_PRODUCT) -> str:
    """Prioritized recommendations for what to work on next, ranked by direction alignment, severity, and impact."""
    from core.engine.mcp.tools import ace_recommend as _recommend

    data = await _recommend(product_id=product_id)

    mode = data.get("mode", "gap_driven")
    recs = data.get("recommendations", [])

    if mode == "innovate" or not recs:
        ws = data.get("whitespace_preview", [])
        lines = ["## Recommendations — Innovate Mode", "", "All quality gaps closed. Top whitespace opportunities:"]
        for w in ws:
            lines.append(f"- {w.get('title', w.get('slug', '?'))} (score: {w.get('whitespace_score', 0):.2f})")
        lines.append("\nRun `ace_innovate` to generate initiatives from these.")
        return "\n".join(lines)

    lines = ["## Recommendations"]
    for n, rec in enumerate(recs[:5], 1):
        cap = rec.get("capability_slug", "?")
        dim = rec.get("dimension", "?")
        score = rec.get("current_score", 0)
        gaps = rec.get("gaps", [])
        lines.append(f"\n**{n}. {dim} · {cap}** (score: {score})")
        for g in gaps[:3]:
            lines.append(f"   - {g}")
        if len(gaps) > 3:
            lines.append(f"   - … +{len(gaps) - 3} more")

    if len(recs) > 5:
        lines.append(f"\n+{len(recs) - 5} more gaps. Use `ace_gaps(dimension=...)` to drill in.")

    return "\n".join(lines)


@mcp.tool(title="Roadmap")
async def ace_roadmap(product_id: str = DEFAULT_PRODUCT) -> str:
    """The living roadmap — what's next, computed fresh from the graph. Canonical; strategy docs are snapshots."""
    from core.engine.mcp.tools import ace_roadmap as _roadmap

    data = await _roadmap(product_id=product_id)

    lanes = data.get("lanes", {})
    lines = ["## Living Roadmap", ""]
    for lane_name in ("now", "next", "blocked", "parked", "done"):
        items = lanes.get(lane_name, [])
        if not items:
            continue
        lines.append(f"### {lane_name.upper()}")
        for item in items:
            title = item.get("title", "?")
            spec = item.get("spec_status") or "—"
            staleness = item.get("staleness", "fresh")
            rationale = item.get("rationale", "")
            blocking = item.get("blocking", [])
            stale_tag = f" ⚠ {staleness}" if staleness != "fresh" else ""
            lines.append(f"- **{title}** · spec: {spec}{stale_tag}")
            if rationale:
                lines.append(f"  {rationale}")
            if blocking:
                lines.append(f"  blocked-by: {', '.join(blocking)}")
        lines.append("")
    if not any(lanes.get(ln) for ln in ("now", "next", "blocked", "parked", "done")):
        lines.append("Nothing planned yet — capture decisions and specs to populate the roadmap.")
    return "\n".join(lines)


@mcp.tool(title="Promote")
async def ace_promote(spec_id: str, product_id: str = DEFAULT_PRODUCT) -> str:
    """Approve a built spec → merge its arm build into base (gate-validated) → shipped."""
    from core.engine.mcp.tools import ace_promote as _promote

    data = await _promote(spec_id=spec_id, product_id=product_id)
    if data.get("promoted"):
        return f"✅ Promoted {spec_id} — merged ({str(data.get('merge_sha', ''))[:10]}) + shipped. Push when ready."
    return f"⛔ Not promoted: {data.get('reason', 'unknown')}"


@mcp.tool(title="Reject")
async def ace_reject(spec_id: str, product_id: str = DEFAULT_PRODUCT) -> str:
    """Reject a built spec's build → discard the worktree → re-queue the spec."""
    from core.engine.mcp.tools import ace_reject as _reject

    data = await _reject(spec_id=spec_id, product_id=product_id)
    return f"↩️ {data.get('reason', 'rejected')}" if data.get("rejected") else f"⛔ {data.get('reason', 'failed')}"


@mcp.tool(title="Build")
async def ace_build(spec_id: str, product_id: str = DEFAULT_PRODUCT) -> str:
    """Build a roadmap spec via an arm → it lands in the review lane to approve."""
    from core.engine.mcp.tools import ace_build as _build

    data = await _build(spec_id=spec_id, product_id=product_id)
    if data.get("built"):
        return f"🔨 Built {spec_id} in {data.get('branch', '')} — in review. ace_promote to ship."
    return f"⛔ Not built: {data.get('reason', 'unknown')}"


@mcp.tool(title="Scan Repo")
async def ace_scan_repo(repo_path: str = ".", product_id: str = DEFAULT_PRODUCT) -> str:
    """Scan the code graph and propose product-level capabilities. Returns proposals for human review — not auto-committed."""
    from core.engine.mcp.tools import ace_scan_repo as _scan

    d = await _scan(repo_path=repo_path, product_id=product_id)
    if d.get("error"):
        return f"✗ Scan failed: {d['error']}"
    status = d.get("status", "?")
    msg = d.get("message", "")
    graph_id = d.get("graph_id", "")
    comp_id = d.get("competitor_id", "")
    lines = [f"◎ Repo scan  ·  {status}", _SEP, msg]
    if graph_id:
        lines.append(f"graph: {graph_id}")
    if comp_id:
        lines.append(f"competitor: {comp_id}")
    return "\n".join(lines)


@mcp.tool(title="Ask")
async def ace_ask_product(question: str, product_id: str = DEFAULT_PRODUCT) -> dict:
    """Ask a question about the product. Creates a product question that ACE will investigate. Questions are categorized and prioritized automatically."""
    from core.engine.mcp.tools import ace_ask_product as _ask

    return await _ask(question=question, product_id=product_id)


@mcp.tool(title="Create Spec")
async def ace_create_spec(description: str, source: str = "human", capability_slug: str | None = None) -> dict:
    """Generate an agent-executable spec. Describe what you want built and ACE produces a detailed spec with acceptance criteria, constraints, integration points, and test requirements. The spec is grounded in the product map and best practices."""
    from core.engine.mcp.tools import ace_create_spec as _create

    return await _create(description=description, source=source, capability_slug=capability_slug)


@mcp.tool(title="Discover")
async def ace_discover(vision: str, product_id: str = DEFAULT_PRODUCT) -> dict:
    """Explore a vague vision into candidate specs — the FRONT of the build->ship loop. Give a fuzzy goal ('make onboarding feel alive'); ACE fans out distinct directions it could take, converges on the best few, and emits them as draft agent_specs (source='discover') for you to review and pick which to build with ace_build."""
    from core.engine.mcp.tools import ace_discover as _discover

    return await _discover(vision=vision, product_id=product_id)


@mcp.tool(title="Submit Feedback")
async def ace_submit_feedback(spec_id: str, feedback_type: str, content: str) -> dict:
    """Report feedback to the PM while working on a spec. Types: blocker (stuck), discovery (found something), trade_off (need decision), scope_question (need clarification), completion (done), progress (update)."""
    from core.engine.mcp.tools import ace_submit_feedback as _feedback

    return await _feedback(spec_id=spec_id, feedback_type=feedback_type, content=content)


@mcp.tool(title="Verify Spec")
async def ace_verify_spec(spec_id: str) -> dict:
    """Verify a completed spec against its acceptance criteria. Checks each criterion, evaluates quality improvement, and flags follow-up work if needed."""
    from core.engine.mcp.tools import ace_verify_spec as _verify

    return await _verify(spec_id=spec_id)


@mcp.tool(title="Export Distillation Corpus")
async def ace_export_distillation(
    discipline: str = "",
    min_confidence: float = 0.7,
    limit: int = 1000,
    product_id: str = DEFAULT_PRODUCT,
) -> str:
    """Export successful STaR traces as fine-tune-ready JSONL.

    Each line is {prompt, completion, metadata}. Filter by discipline and minimum
    confidence. Feed the output to Anthropic batch API, OpenAI fine-tune, or any
    other training pipeline to distill ACE's captured reasoning into a smaller model.
    """
    from core.engine.core.db import pool as default_pool
    from core.engine.intelligence.distillation_export import export_distillation_jsonl

    async with default_pool.connection() as db:
        return await export_distillation_jsonl(
            db=db,
            product_id=product_id,
            discipline=discipline or None,
            min_confidence=min_confidence,
            limit=limit,
        )


@mcp.tool(title="Export Intelligence Pack")
async def ace_export_pack(
    discipline: str,
    product_id: str = DEFAULT_PRODUCT,
    limit: int = 50,
) -> str:
    """Export ACE intelligence as a portable markdown prompt pack for the given discipline.

    The returned document can be prepended to any LLM agent's system prompt to
    inherit ACE's accumulated insights, decisions, corrections, and proven
    reasoning patterns for this product + discipline — no live ACE runtime needed.
    """
    from core.engine.core.db import pool as default_pool
    from core.engine.intelligence.export_pack import export_prompt_pack

    async with default_pool.connection() as db:
        return await export_prompt_pack(db=db, product_id=product_id, discipline=discipline, limit=limit)


@mcp.tool(title="Capture Decision")
async def ace_capture_decision(
    title: str,
    decision_type: str,
    rationale: str,
    alternatives: list[str] | None = None,
    affected_capabilities: list[str] | None = None,
) -> str:
    """Record a PM decision with rationale and alternatives considered. Types: architecture, prioritization, trade_off, direction, rejection, convention."""
    from core.engine.mcp.tools import ace_capture_decision as _capture

    d = await _capture(
        title=title,
        decision_type=decision_type,
        rationale=rationale,
        alternatives=alternatives,
        affected_capabilities=affected_capabilities,
    )
    dec_id = str(d.get("id", ""))
    lines = [
        f"🔷 Decision recorded  ·  {decision_type}",
        _SEP,
        title,
        f"why: {rationale[:200]}",
    ]
    if alternatives:
        lines.append("alts: " + "  |  ".join(alternatives[:4]))
    if affected_capabilities:
        lines.append("caps: " + ", ".join(affected_capabilities[:4]))
    if dec_id:
        lines.append(f"→ {dec_id}")
    return "\n".join(lines)


@mcp.tool(title="Active Composition")
async def ace_active_composition(product_id: str = DEFAULT_PRODUCT) -> str:
    """Show 'the orchestra' — which meta-intelligences self-nominated for the most recent task. Returns active meta-skills, depth, fusion mode, classification, and phase sequence. Use this to see what ACE is currently composing without subscribing to the canvas event stream."""
    from core.engine.mcp.tools import ace_active_composition as _active

    result = await _active(product_id=product_id)
    composition = result.get("composition")
    if composition is None:
        return result.get("note", "No active composition.")

    meta_skills = composition.get("meta_skills", [])
    depth = composition.get("depth")
    fusion_mode = composition.get("fusion_mode")
    classification = composition.get("classification", {})
    phases = composition.get("phases", [])

    lines = [
        f"🎼 Active Composition  ·  product:{product_id.split(':', 1)[-1] if ':' in product_id else product_id}",
        _SEP,
        f"depth: {depth}    fusion_mode: {fusion_mode}",
        "meta-skills (orchestra):",
    ]
    for slug in meta_skills:
        lines.append(f"  • {slug.replace('_intelligence', '')}")
    if classification:
        cl = (
            f"classification: discipline={classification.get('discipline', '—')}  "
            f"task_type={classification.get('task_type', '—')}  "
            f"mode={classification.get('mode', '—')}  "
            f"archetype={classification.get('archetype', '—')}"
        )
        lines.append(cl)
    if phases:
        lines.append("phases: " + " → ".join(phases))
    return "\n".join(lines)


@mcp.tool(title="Decisions")
async def ace_list_decisions(decision_type: str | None = None, limit: int = 20) -> str:
    """List recent decisions, optionally filtered by type (architecture, prioritization, trade_off, direction, rejection, convention)."""
    from core.engine.mcp.tools import ace_list_decisions as _list

    d = await _list(decision_type=decision_type, limit=limit)
    decisions = d.get("decisions", [])
    filter_label = f"  ·  {decision_type}" if decision_type else ""
    lines = [f"🔷 Decisions{filter_label}  ·  {len(decisions)}", _SEP]

    for dec in decisions:
        title = dec.get("title", "?")
        dtype = dec.get("decision_type", "")
        outcome = dec.get("outcome", "")
        date = str(dec.get("created_at", ""))[:10]
        outcome_tag = f"  [{outcome}]" if outcome and outcome != "accepted" else ""
        type_tag = f"  {dtype}" if dtype else ""
        lines.append(f"🔷{type_tag}{outcome_tag}  {title}  ({date})")
        rationale = dec.get("rationale", "")
        if rationale:
            lines.append(f"   why: {rationale[:120]}")

    if not decisions:
        lines.append("No decisions recorded yet.")

    return "\n".join(lines)


@mcp.tool(title="Link Decisions")
async def ace_link_decisions(dry_run: bool = False) -> dict:
    """Auto-link decisions to capabilities and git commits via keyword matching. Creates affected (decision→capability) and manifested_by (decision→commit) edges. Idempotent — safe to re-run. Use dry_run=True to preview links without writing."""
    from core.engine.mcp.tools import ace_link_decisions as _link

    return await _link(dry_run=dry_run)


@mcp.tool(title="Trace")
async def ace_trace(node_id: str) -> str:
    """Traverse the traceability graph from any node. Pass any record ID: decision:x, capability:x, graph_file:x, graph_decision:x. Returns all directly connected nodes in every direction."""
    from core.engine.mcp.tools import ace_trace as _trace

    d = await _trace(node_id=node_id)
    if d.get("error"):
        return f"✗ {d['error']}"

    node = d.get("node", {})
    table = node_id.split(":")[0] if ":" in node_id else "node"
    label = node.get("title") or node.get("name") or node.get("path") or node.get("slug") or node_id
    lines = [f"◈ Trace  ·  {table}  ·  {label}", _SEP]

    connections = d.get("connections", {})
    for rel, items in connections.items():
        if not items:
            continue
        lines.append(f"\n{rel} ({len(items)})")
        for item in items[:8]:
            name = (
                item.get("title")
                or item.get("name")
                or item.get("path")
                or item.get("slug")
                or str(item.get("id", "?"))
            )
            lines.append(f"  → {name}")
        if len(items) > 8:
            lines.append(f"  … +{len(items) - 8} more")

    if not any(connections.values()):
        lines.append("No connections found.")

    return "\n".join(lines)


@mcp.tool(title="Export Decisions")
async def ace_export_decisions(
    output_path: str = ".ace/decisions.yml",
    mode: str = "warn",
) -> dict:
    """Export accepted decisions to .ace/decisions.yml lockfile for offline enforcement. Run after ace_capture_decision to keep enforcement current. mode: warn (advisory) | block (blocks writes)."""
    from core.engine.mcp.tools import ace_export_decisions as _export

    return await _export(output_path=output_path, mode=mode)


@mcp.tool(title="Enforce")
async def ace_enforce(action: str, target: str | None = None) -> str:
    """Enforcement engine control. action: status (lockfile age + decision count) | check <file> (check specific file) | check-staged (check all staged git files) | install-hook (add pre-commit hook) | regen (re-export lockfile from DB)."""
    from core.engine.mcp.tools import ace_enforce as _enforce

    d = await _enforce(action=action, target=target)
    if d.get("error"):
        return f"✗ {d['error']}"

    if action == "status":
        exists = d.get("lockfile_exists", False)
        lock_icon = "🔒" if exists else "🔓"
        age = d.get("lockfile_age_hours")
        count = d.get("decisions_exported", 0)
        age_str = f"  ·  {age}h old" if age is not None else ""
        lines = [
            f"{lock_icon} Enforce status",
            _SEP,
            f"lockfile: {'exists' if exists else 'missing'}{age_str}",
            f"decisions: {count}",
            f"config: {'✓' if d.get('config_exists') else '✗ missing'}",
        ]
        return "\n".join(lines)

    if action in ("check", "check-staged"):
        violations = d.get("violations", [])
        checked = d.get("files_checked", d.get("file", target or "?"))
        lines = [f"{'✗' if violations else '✓'} Enforce check  ·  {checked}", _SEP]
        for v in violations:
            lines.append(f"  ✗ {v.get('rule', '?')}  {v.get('file', '')}")
            if v.get("message"):
                lines.append(f"    {v['message'][:120]}")
        if not violations:
            lines.append("No violations.")
        return "\n".join(lines)

    if action == "install-hook":
        ok = d.get("status") == "installed" or d.get("installed")
        return f"{'✓' if ok else '✗'} Git pre-commit hook {'installed' if ok else 'failed'}"

    if action == "regen":
        exported = d.get("exported", 0)
        path = d.get("output_path", ".ace/decisions.yml")
        return f"✓ Lockfile regenerated  ·  {exported} decisions  →  {path}"

    # Fallback for unknown actions
    return str(d)


@mcp.tool(title="Scan Hardening")
async def ace_scan_hardening(
    repo_path: str = ".",
    stack_override: list[str] | None = None,
    fast: bool = False,
    store: bool = True,
) -> dict:
    """Run full static analysis suite. Dispatches Semgrep (OWASP) + TruffleHog always; adds Bandit + Ruff + pip-audit for Python stack. Returns Production Readiness Report with ranked findings by severity × discipline priority. Results stored in capability_finding table."""
    from core.engine.mcp.tools import ace_scan_hardening as _scan

    return await _scan(repo_path=repo_path, stack_override=stack_override, fast=fast, store=store)


@mcp.tool(title="Findings")
async def ace_findings(
    discipline: str | None = None,
    severity: str | None = None,
    file_path: str | None = None,
    unresolved_only: bool = True,
    limit: int = 50,
) -> str:
    """Query persisted static analysis findings from ace_scan_hardening. Filter by discipline (security|testing|code_conventions|dependency_management|...), severity (critical|high|medium|low|info), or file path. Use to drill into discipline failures from ace_product_health scores."""
    from core.engine.mcp.tools import ace_findings as _findings

    d = await _findings(
        discipline=discipline,
        severity=severity,
        file_path=file_path,
        unresolved_only=unresolved_only,
        limit=limit,
    )
    return _fmt_findings(d)


@mcp.tool(title="Cost Estimate")
async def ace_cost_estimate(
    users: int = 1000,
    providers: list[str] | None = None,
) -> dict:
    """Estimate monthly infrastructure + API costs at a given user scale. Three passes: (1) query anti-patterns from graph, (2) compute topology detection, (3) third-party API integrations (OpenAI, Stripe, SendGrid). Returns breakdown per provider + optimization recommendations."""
    from core.engine.mcp.tools import ace_cost_estimate as _cost

    return await _cost(users=users, providers=providers)


@mcp.tool(title="Generate CI")
async def ace_generate_ci(
    target: str = "github_actions",
    repo_path: str = ".",
) -> dict:
    """Generate a CI/CD workflow file parameterized from the ACE code graph. Target: 'github_actions', 'gitlab_ci', 'circleci'. Reads discipline gap profile to set coverage gates calibrated to current quality scores."""
    from core.engine.mcp.tools import ace_generate_ci as _gen_ci

    return await _gen_ci(target=target, repo_path=repo_path)


@mcp.tool(title="Generate Deploy")
async def ace_generate_deploy(
    target: str = "docker_compose",
    repo_path: str = ".",
) -> dict:
    """Generate a deployment manifest from the ACE code graph. Target: 'docker_compose', 'railway', 'coolify', 'kamal'. Detects services, ports, and DBs from your capability graph — not a generic template."""
    from core.engine.mcp.tools import ace_generate_deploy as _gen_deploy

    return await _gen_deploy(target=target, repo_path=repo_path)


@mcp.tool(title="Generate Docs")
async def ace_generate_docs(
    format: str = "onboarding_guide",
    repo_path: str = ".",
) -> dict:
    """Generate docs from the ACE intelligence graph. Format: 'mermaid' (architecture diagram), 'onboarding_guide' (stack + conventions + gotchas), 'api_reference' (API surface). All enriched with captured decisions."""
    from core.engine.mcp.tools import ace_generate_docs as _gen_docs

    return await _gen_docs(format=format, repo_path=repo_path)


@mcp.tool(title="Changelog")
async def ace_changelog(
    since_tag: str | None = None,
    max_entries: int = 50,
    repo_path: str = ".",
) -> dict:
    """Generate a decision-enriched changelog from git history. Reads git log since since_tag (or last 50 commits) and enriches each entry with captured decision rationale — linking code changes to their 'why'."""
    from core.engine.mcp.tools import ace_changelog as _changelog

    return await _changelog(since_tag=since_tag, max_entries=max_entries, repo_path=repo_path)


@mcp.tool(title="Instrument")
async def ace_instrument(
    stack: list[str] | None = None,
    repo_path: str = ".",
) -> dict:
    """Generate production-ready OpenTelemetry config for the detected stack. Auto-detects Python/FastAPI or Node.js/TypeScript from the capability graph. Returns otel_config.py or otel.ts, docker-compose.otel.yml, and collector config. Ready to drop into repo root."""
    from core.engine.mcp.tools import ace_instrument as _instrument

    return await _instrument(stack=stack, repo_path=repo_path)


@mcp.tool(title="Explain Error")
async def ace_explain_error(
    error: str,
    stack_trace: str = "",
) -> dict:
    """Explain a runtime error using ACE intelligence + decision graph. Parses stack trace → loads relevant decisions → checks runbook table for known patterns → LLM synthesis. Auto-captures new patterns as runbooks (compounds over time)."""
    from core.engine.mcp.tools import ace_explain_error as _explain

    return await _explain(error=error, stack_trace=stack_trace)


@mcp.tool(title="Update Deps")
async def ace_update_deps(
    strategy: str = "minor",
    repo_path: str = ".",
) -> dict:
    """Generate a decision-aware dependency update plan. Runs pip-audit + npm audit, then cross-references with ACE decisions. Packages pinned in decisions are flagged as blocked with rationale. Strategy: 'patch', 'minor', or 'semver'."""
    from core.engine.mcp.tools import ace_update_deps as _update_deps

    return await _update_deps(strategy=strategy, repo_path=repo_path)


@mcp.tool(title="Seam Check")
async def ace_seam_check(
    product_id: str = DEFAULT_PRODUCT,
    severity: str | None = None,
    route: str | None = None,
) -> dict:
    """Check for API contract mismatches between backend endpoints and frontend consumers. Returns seam gaps with severity (error/warning/info). Call after code changes to verify backend-frontend contracts are aligned."""
    from core.engine.mcp.tools import ace_seam_check as _check

    return await _check(severity=severity, route=route, product_id=product_id)


@mcp.tool(title="Pending Gates")
async def ace_pending_gates(product_id: str = DEFAULT_PRODUCT) -> str:
    """List all entities waiting for quality gate review (spec review, plan review, initiative review)."""
    from core.engine.mcp.tools import ace_pending_gates as _pending

    d = await _pending(product_id=product_id)
    items = d.get("gates", d.get("items", []))
    return _fmt_gates(items)


@mcp.tool(title="Spec Reality Check")
async def ace_spec_reality_check(product_id: str = DEFAULT_PRODUCT) -> str:
    """Which of your draft/approved specs are ALREADY BUILT? Run before approving anything: the
    backlog is the last lying instrument, and it sits directly upstream of an autonomous builder.
    Five of sixteen drafts audited by hand were already fully implemented."""
    from core.engine.mcp.tools import ace_spec_reality_check as _check

    d = await _check(product_id=product_id)
    rows = d.get("already_built") or []
    if not rows:
        return (
            "No spec NAMES a file that already exists, and the graph evidence was inconclusive.\n\n"
            "Read that precisely: this is a CHEAP FIRST PASS, not an audit. It reliably catches a spec "
            "that says 'create X.py' when X.py is on disk. It CANNOT tell you whether 'implement seven "
            "memory enhancements' is already done — measured: it missed 3 of 3 such specs, because "
            "proving that needs someone to actually read the files, which is what found the five stale "
            "specs in the first place. A clean result here is not a clean backlog."
        )
    lines = [f"{len(rows)} spec(s) appear ALREADY BUILT — do not approve these, close them:\n"]
    for r in rows:
        lines.append(f"• [{r['confidence']}] {r['objective']}")
        for e in r["evidence"][:3]:
            lines.append(f"      {e}")
        lines.append(f"      {r['spec']}")
    return "\n".join(lines)


@mcp.tool(title="Provider Probe")
async def ace_provider_probe() -> str:
    """Can the currently configured model actually DRIVE the build loop? Tests the three contracts
    the arms depend on — structured output (router + critic), strict-JSON codegen, whole-file output
    — against whatever provider is configured. Run this BEFORE pointing ACE at a new/local/open
    model: it costs a minute and tells you which capability is missing and what that will break,
    instead of you discovering it after a night of parked builds."""
    from core.engine.mcp.tools import ace_provider_probe as _probe

    d = await _probe()
    return d.get("report") or f"probe failed: {d.get('diagnosis', 'unknown')}"


@mcp.tool(title="Build Session")
async def ace_build_session(product_id: str = DEFAULT_PRODUCT, max_builds: int = 5) -> str:
    """Run an UNATTENDED build session: build approved specs one at a time (each in a fresh context)
    until the work, the budget, or the engine's health runs out. It stops ITSELF on a parked build
    (the environment broke — every further build would park identically) or on a run of consecutive
    failures (something systemic is wrong), rather than grinding the whole backlog into failed
    builds. Check ace_parked_runs afterwards for anything waiting on you."""
    from core.engine.mcp.tools import ace_build_session as _session

    d = await _session(product_id=product_id, max_builds=max_builds)
    lines = [f"Build session stopped: {d['stopped_because']}"]
    if d.get("reconciled_zombies"):
        lines.append(f"(reconciled {d['reconciled_zombies']} interrupted run(s) from a dead process)")
    if d.get("released_specs"):
        lines.append(f"(released {d['released_specs']} spec(s) stranded in 'building' by a dead process)")
    lines.append(f"\nBuilt {len(d['built'])}, failed {len(d['failed'])}.")
    for b in d["built"]:
        lines.append(f"  ✓ {b['spec']} → {b.get('branch') or '(no branch)'}")
    for f in d["failed"]:
        lines.append(f"  ✗ {f['spec']}: {f.get('reason', '')[:120]}")
    # ALWAYS report the draft count. An empty queue is ambiguous until you know it: "everything is
    # done" and "nothing is authorised" look identical from inside the loop.
    if d.get("awaiting_approval"):
        lines.append(f"\n{d['awaiting_approval']} spec(s) await YOUR approval (ace_approve_gate) — not yet buildable.")
    if d.get("needs_human"):
        lines.append(f"\n⚠ NEEDS YOU: {d.get('diagnosis', '')}")
    return "\n".join(lines)


@mcp.tool(title="Parked Runs")
async def ace_parked_runs(product_id: str = DEFAULT_PRODUCT) -> str:
    """Builds that stopped and need a human: PARKED (the environment broke mid-build — the work was
    never judged and its workspace is preserved) or RUNNING (a process killed mid-build, never
    finalized). Failed builds are not listed: those were judged, were wrong, and were discarded.
    Call this after any unattended build session to see what is waiting on you."""
    from core.engine.mcp.tools import ace_parked_runs as _parked

    d = await _parked(product_id=product_id)
    runs = d.get("runs", [])
    if not runs:
        return "No parked or interrupted builds — nothing is waiting on you."
    lines = [f"{d['count']} build(s) need a human:\n"]
    for r in runs:
        state = "PARKED" if r["status"] == "parked" else "INTERRUPTED (process died mid-build)"
        lines.append(f"• [{state}] {r['arm_domain']}: {r['intent']}")
        lines.append(f"    attempts: {r['attempts']}  ·  {r['id']}")
        if r.get("diagnosis"):
            lines.append(f"    fix: {r['diagnosis']}")
    return "\n".join(lines)


@mcp.tool(title="Approve Gate")
async def ace_approve_gate(entity_type: str, entity_id: str, rationale: str = "") -> str:
    """Approve a pending quality gate. Creates a decision record and transitions the entity forward."""
    from core.engine.mcp.tools import ace_approve_gate as _approve

    d = await _approve(entity_type, entity_id, rationale)
    status = d.get("status", "approved")
    lines = [f"✓ Gate Approved  ·  {entity_type}  ·  {entity_id}", _SEP]
    if rationale:
        lines.append(f"Rationale: {rationale}")
    lines.append(f"Status: {status}")
    return "\n".join(lines)


@mcp.tool(title="Reject Gate")
async def ace_reject_gate(entity_type: str, entity_id: str, reason: str) -> str:
    """Reject a pending quality gate with reason. Transitions the entity back for rework."""
    from core.engine.mcp.tools import ace_reject_gate as _reject

    d = await _reject(entity_type, entity_id, reason)
    status = d.get("status", "rejected")
    lines = [f"✗ Gate Rejected  ·  {entity_type}  ·  {entity_id}", _SEP]
    lines.append(f"Reason: {reason}")
    lines.append(f"Status: {status}")
    return "\n".join(lines)


@mcp.tool(title="Self Audit")
async def ace_self_audit(
    gaps_only: bool = False,
    budget: int = 50,
    product_id: str = DEFAULT_PRODUCT,
) -> dict:
    """Run ACE on itself — loads human-verified capabilities into the product map, then evaluates each against quality disciplines. Returns gap report with worst scores. Use gaps_only=True to skip reloading capabilities."""
    from core.engine.mcp.tools import ace_self_audit as _self_audit

    return await _self_audit(gaps_only=gaps_only, budget=budget, product_id=product_id)


@mcp.tool(title="Context")
async def ace_context(product_id: str = DEFAULT_PRODUCT) -> dict:
    """Full session context — what's built, quality, decisions, gaps, active work.
    Call at start of implementation sessions for complete orientation."""
    from core.engine.mcp.tools import ace_context as _context

    return await _context(product_id)


@mcp.tool(title="PR Review")
async def ace_pr_review(
    pr_url: str = "",
    source: str = "",
    disciplines: list[str] | None = None,
    post_review: bool = False,
) -> dict:
    """Review a GitHub/GitLab PR or local git branch using ACE's 18-discipline intelligence.

    Runs parallel discipline-specific review passes (security, architecture,
    testing, etc.), synthesizes findings with a judge agent, and returns
    a quality gate verdict. Optionally posts review comments back to the platform.

    source formats:
    - "local" or "local:/path/to/repo" — review current branch vs main
    - "github:owner/repo#123" — GitHub PR
    - "gitlab:group/project!42" — GitLab MR
    - Or pass pr_url for GitHub PR URLs (backward compatible)
    """
    from core.engine.mcp.tools import ace_pr_review as _review

    return await _review(pr_url=pr_url, source=source, disciplines=disciplines, post_review=post_review)


@mcp.tool(title="Generate Tests")
async def ace_generate_tests(
    capability_slug: str = "",
    acceptance_criteria: list[str] | None = None,
    context: str = "",
) -> dict:
    """Generate test suites from capability specs or acceptance criteria.

    Provide either a capability_slug to load the spec from DB,
    or pass acceptance_criteria directly as a list of strings.
    Returns rendered test code ready to save to a file.
    """
    from core.engine.mcp.tools import ace_generate_tests as _gen

    return await _gen(
        capability_slug=capability_slug,
        acceptance_criteria=acceptance_criteria,
        context=context,
    )


@mcp.tool(title="Add Product")
async def ace_add_product(
    name: str,
    repo_path: str | None = None,
    description: str | None = None,
    ecosystem_slug: str | None = None,
    active_disciplines: list[str] | None = None,
) -> dict:
    """Add a product to the portfolio. Creates a project record for ACE to manage.

    Use this when the user wants to onboard a new codebase or product. Provide at minimum the name.
    If a repo_path is given, ACE will scan it to detect the stack and capabilities.
    Use ecosystem_slug to group related codebases (e.g., frontend + backend of the same product).
    """
    from core.engine.mcp.tools import ace_add_product as _add

    return await _add(
        name=name,
        repo_path=repo_path,
        description=description,
        ecosystem_slug=ecosystem_slug,
        active_disciplines=active_disciplines,
    )


@mcp.tool(title="Symbol Importance")
async def ace_symbol_importance(limit: int = 20, product_id: str = DEFAULT_PRODUCT) -> dict:
    """Get the most architecturally important files ranked by graph centrality."""
    from core.engine.mcp.tools import ace_symbol_importance as _fn

    return await _fn(limit=limit, product_id=product_id)


@mcp.tool(title="Blast Radius")
async def ace_blast_radius(target: str, product_id: str = DEFAULT_PRODUCT) -> dict:
    """Analyze blast radius: what files are affected if this file/symbol changes?"""
    from core.engine.mcp.tools import ace_blast_radius as _fn

    return await _fn(target=target, product_id=product_id)


@mcp.tool(title="Dead Code")
async def ace_find_dead_code(product_id: str = DEFAULT_PRODUCT) -> dict:
    """Find symbols and files that nothing references (potentially dead code)."""
    from core.engine.mcp.tools import ace_find_dead_code as _fn

    return await _fn(product_id=product_id)


@mcp.tool(title="Code Context")
async def ace_code_context(query: str, product_id: str = DEFAULT_PRODUCT) -> dict:
    """Graph-aware RAG: extract code context relevant to a natural language query."""
    from core.engine.mcp.tools import ace_code_context as _fn

    return await _fn(query=query, product_id=product_id)


@mcp.tool(title="Search Code")
async def ace_search_code(query: str, limit: int = 10) -> dict:
    """Search the codebase semantically — finds related code by meaning, not just filename."""
    from core.engine.mcp.tools import ace_search_code as _fn

    return await _fn(query=query, limit=limit)


@mcp.tool(title="Smart Outline")
async def ace_smart_outline(file_path: str) -> dict:
    """Parse a source file with AST — returns functions, classes, imports without a full read."""
    from core.engine.mcp.tools import ace_smart_outline as _fn

    return await _fn(file_path=file_path)


@mcp.tool(title="Smart Search")
async def ace_smart_search(
    query: str,
    product_id: str = DEFAULT_PRODUCT,
    limit: int = 10,
) -> dict:
    """Search code graph by symbol/file name using BM25 (fn_search index).
    Complements ace_search_code (semantic); this is identifier-focused."""
    from core.engine.mcp.tools import ace_smart_search as _fn

    return await _fn(query=query, product_id=product_id, limit=limit)


@mcp.tool(title="Smart Unfold")
async def ace_smart_unfold(
    symbol: str,
    file_path: str | None = None,
    product_id: str = DEFAULT_PRODUCT,
    depth: int = 1,
) -> dict:
    """Progressive context expansion from a symbol: definition + callers/callees + recent observations."""
    from core.engine.mcp.tools import ace_smart_unfold as _fn

    return await _fn(symbol=symbol, file_path=file_path, product_id=product_id, depth=depth)


@mcp.tool(title="Dependency Chain")
async def ace_dependency_chain(from_file: str, to_file: str, product_id: str = DEFAULT_PRODUCT) -> dict:
    """Find the shortest dependency path between two files."""
    from core.engine.mcp.tools import ace_dependency_chain as _fn

    return await _fn(from_file=from_file, to_file=to_file, product_id=product_id)


@mcp.tool(title="Module Coupling")
async def ace_module_coupling(module_a: str, module_b: str, product_id: str = DEFAULT_PRODUCT) -> dict:
    """Measure coupling between two modules/directories."""
    from core.engine.mcp.tools import ace_module_coupling as _fn

    return await _fn(module_a=module_a, module_b=module_b, product_id=product_id)


@mcp.tool(title="Research")
async def ace_research(
    topic: str,
    research_type: str = "grounded_how_to",
    product_id: str = DEFAULT_PRODUCT,
    ceiling: str = "sonnet",
) -> dict:
    """Run multi-mode research on a topic and write synthesis to the intelligence graph.

    research_type options:
      "internal"        — Query ACE graph only (zero web calls, instant)
      "grounded_how_to" — How should WE implement X given our stack? (default)
      "competitive"     — What is the landscape? What are others building?
      "greenfield"      — What should we build and why? (Opus, strategic synthesis)
    """
    from core.engine.mcp.tools import ace_research as _research

    return await _research(topic=topic, research_type=research_type, product_id=product_id, ceiling=ceiling)


@mcp.tool(title="Web Fetch")
async def ace_web_fetch(url: str, mode: str = "auto") -> dict:
    """Fetch any URL and return clean markdown. Bypasses anti-bot protection.

    mode options:
      "auto"    — try curl_cffi → scrapling → patchright → httpx (default)
      "fast"    — curl_cffi → httpx only (no browser launch)
      "stealth" — scrapling StealthyFetcher (camoufox, best for Cloudflare/DataDome)
      "cdp"     — patchright Chrome CDP (for JS-heavy/interactive pages)
    """
    from core.engine.mcp.tools import ace_web_fetch as _fn

    return await _fn(url=url, mode=mode)


@mcp.tool(title="Web Search")
async def ace_web_search(query: str, limit: int = 10, fetch_content: bool = False) -> dict:
    """Search the web and return results. Optionally fetch full content of top results.

    Uses DuckDuckGo (no API key) with Tavily fallback if TAVILY_API_KEY is set.
    Set fetch_content=True to return full markdown for each result (slower).
    """
    from core.engine.mcp.tools import ace_web_search as _fn

    return await _fn(query=query, limit=limit, fetch_content=fetch_content)


@mcp.tool(title="Competitor Matrix")
async def ace_competitor_matrix(product_id: str = "product:platform") -> dict:
    """Return the capability matrix: competitor × capability → coverage (full/partial/none).

    Shows which capabilities each competitor covers. Empty cells are our
    differentiation surface. Use this to identify moats and gaps at a glance.
    """
    from core.engine.mcp.tools import ace_competitor_matrix as _fn

    return await _fn(product_id=product_id)


@mcp.tool(title="Whitespace")
async def ace_whitespace(
    product_id: str = "product:platform",
    limit: int = 10,
    min_score: float = 0.0,
) -> dict:
    """Return top whitespace opportunities sorted by score (highest first).

    Whitespace Score = pain_intensity × user_count × (1 - max_competitor_coverage)
                     × feasibility_coefficient × timing_coefficient

    Higher score = better opportunity to differentiate ACE from competitors.
    """
    from core.engine.mcp.tools import ace_whitespace as _fn

    return await _fn(product_id=product_id, limit=limit, min_score=min_score)


@mcp.tool(title="Innovate")
async def ace_innovate(
    mode: str = "all",
    product_id: str = "product:platform",
) -> dict:
    """Run innovation mode(s) for when all gaps are closed.

    mode: "frontier" | "cross_domain" | "emerging_tech" | "compounding" | "all"
    - frontier:      A++ beyond current best practices (papers, tooling, adjacent industries)
    - cross_domain:  Patterns from aviation, film, manufacturing mapped to ACE
    - emerging_tech: New model capabilities → new ACE capabilities
    - compounding:   Features that make other features better over time
    - all:           Run all four modes sequentially (default)
    """
    from core.engine.mcp.tools import ace_innovate as _fn

    return await _fn(mode=mode, product_id=product_id)


@mcp.tool(title="Competitors")
async def ace_list_competitors(product_id: str = "product:platform") -> dict:
    """List all tracked competitors and their scan status.

    Returns each competitor with name, tier, last_scanned, and signal count.
    """
    from core.engine.mcp.tools import ace_list_competitors as _fn

    return await _fn(product_id=product_id)


@mcp.tool(title="Competitor Signals")
async def ace_competitor_signals(
    competitor: str,
    product_id: str = "product:platform",
    min_relevance: float = 0.0,
    limit: int = 20,
) -> dict:
    """Fetch competitive signals for a specific competitor.

    competitor:    Name, e.g. "paul-gauthier/aider" or "All-Hands-AI/OpenHands"
    min_relevance: Filter by minimum relevance_score (0.0–1.0)
    limit:         Max signals to return
    """
    from core.engine.mcp.tools import ace_competitor_signals as _fn

    return await _fn(competitor=competitor, product_id=product_id, min_relevance=min_relevance, limit=limit)


@mcp.tool(title="Scan Competitors")
async def ace_scan_competitors(
    product_id: str = "product:platform",
    github_urls: list[str] | None = None,
    tier: int = 2,
) -> dict:
    """Clone and deep-scan a batch of competitor repos.

    github_urls: list of GitHub URLs or owner/repo slugs to scan and register.
                 If omitted, rescans all existing competitors in DB.
    tier: 1=direct, 2=adjacent, 3=inspirational (used when registering new repos)
    """
    from core.engine.mcp.tools import ace_scan_competitors as _fn

    return await _fn(product_id=product_id, github_urls=github_urls, tier=tier)


@mcp.tool(title="Agent Verified")
async def ace_agent_verified(
    task: str,
    criteria: list[str],
    product_id: str = DEFAULT_PRODUCT,
    model: str | None = None,
    max_iterations: int = 3,
) -> dict:
    """Run an agentic task with iterative grader verification.

    Agents do NOT see the criteria — only the isolated GraderAgent subprocess does.
    Loops: ace_agent → grade → unmet feedback → retry → until satisfied or max_iterations.
    Returns verdict ("satisfied" | "max_iterations_reached"), per-iteration grades, token counts, cost.
    Use instead of ace_agent when verifiable completion matters.
    """
    from core.engine.mcp.tools import ace_agent_verified as _fn

    return await _fn(
        task=task,
        criteria=criteria,
        product_id=product_id,
        model=model,
        max_iterations=max_iterations,
    )


@mcp.tool(title="Benchmark")
async def ace_benchmark(
    task: str,
    rubric: list[str],
    discipline: str = "",
    product_id: str = DEFAULT_PRODUCT,
    model: str | None = None,
    max_turns: int = 20,
) -> dict:
    """Benchmark ACE vs baseline on a task using an isolated grader.

    Runs the same task through two runtimes with identical model and infrastructure:
    - Baseline: no ACE intelligence (raw LLM)
    - ACE: full cognitive composition + discipline loading + graph insights

    An isolated GraderAgent subprocess (no session history, no ACE context) evaluates
    both outputs against the same rubric. Returns quality delta, token delta, cost delta,
    and ROI (quality gain per dollar of ACE overhead). Persists to benchmark_result table
    for discipline-level trend analysis over time.
    """
    from core.engine.mcp.tools import ace_benchmark as _fn

    return await _fn(
        task=task,
        rubric=rubric,
        discipline=discipline,
        product_id=product_id,
        model=model,
        max_turns=max_turns,
    )


@mcp.tool(title="Discovery Sprint")
async def ace_discovery_sprint(
    client_name: str,
    product_id: str = DEFAULT_PRODUCT,
    loaded_hourly_rate: float = 150.0,
) -> dict:
    """Generate a client-ready discovery sprint report for an MSP engagement.

    Runs gaps + recommendations through the packager to produce:
    - Executive summary (plain language, no jargon, ≤300 words)
    - Top 5 automation candidates with grounded ROI (hours/week × rate × 52 weeks)
    - Spec stubs passable directly to ace_create_spec
    - Full markdown export (Notion/Google Docs/email ready) + JSON

    Use this after ace_scan_repo to generate a client deliverable.
    """
    from core.engine.mcp.tools import ace_discovery_sprint as _fn

    return await _fn(
        client_name=client_name,
        product_id=product_id,
        loaded_hourly_rate=loaded_hourly_rate,
    )


@mcp.tool(title="Retainer Status")
async def ace_retainer_status(
    product_id: str = DEFAULT_PRODUCT,
    record_delivery_spec_id: str | None = None,
    record_delivery_title: str | None = None,
) -> dict:
    """Get engagement state and next retainer expansion for a client product.

    Shows delivery history, surfaces the next undelivered automation candidate,
    and generates a retainer framing pitch ("we automated X, here's Y which unlocks Z").

    Pass record_delivery_spec_id + record_delivery_title to record a new delivery
    before computing the next expansion.
    """
    from core.engine.mcp.tools import ace_retainer_status as _fn

    return await _fn(
        product_id=product_id,
        record_delivery_spec_id=record_delivery_spec_id,
        record_delivery_title=record_delivery_title,
    )


@mcp.tool(title="Query Discipline")
async def ace_query_discipline(
    discipline: str,
    question: str,
    product_id: str = DEFAULT_PRODUCT,
) -> dict:
    """Ask a question against ACE's accumulated knowledge for a specific discipline.

    Queries insights, decisions, and capabilities captured for this discipline, then
    answers using an LLM grounded in that product intelligence.

    Example: ace_query_discipline("ux", "what design decisions have been made for the portal?")
    """
    from core.engine.mcp.tools import ace_query_discipline as _fn

    return await _fn(discipline=discipline, question=question, product_id=product_id)


@mcp.tool(title="ACE Health")
async def ace_health(product_id: str = DEFAULT_PRODUCT) -> str:
    """Is ACE working? Check pipeline health: hook fires, capture counts, synthesis status. Returns healthy/degraded/down with a one-sentence 'why not?' when broken."""
    from core.engine.mcp.tools import ace_health as _fn

    d = await _fn(product_id=product_id)
    status = d.get("status", "unknown")
    icon = {"healthy": "✓", "degraded": "⚠", "down": "✗", "recovered": "↺"}.get(status, "○")
    summary = d.get("summary", "")

    lines = [
        f"{icon} ACE Health  ·  {status.upper()}",
        _SEP,
        f"  {summary}",
        "",
        f"  Hook fires:      {d.get('hook_post_count', 0)}",
        f"  Captures:        {d.get('capture_count', 0)}",
        f"  Decisions today: {d.get('decisions_today', 0)}",
        f"  Obs today:       {d.get('observations_today', 0)}",
    ]

    if d.get("uptime_seconds") is not None:
        uptime_min = round(d["uptime_seconds"] / 60)
        lines.append(f"  Worker uptime:       {uptime_min}m")

    if d.get("last_error"):
        lines.append(f"\n  Last error: {d['last_error']}")

    return "\n".join(lines)


@mcp.tool(title="ACE Forecast")
async def ace_forecast(product_id: str = DEFAULT_PRODUCT) -> str:
    """Open predictions — what ACE predicted would change and when to verify."""
    from core.engine.mcp.tools import ace_forecast as _fn

    d = await _fn(product_id=product_id)
    total = d.get("total_open", 0)
    lines = [f"◈ ACE Forecast  ·  {total} open prediction{'s' if total != 1 else ''}  ·  {product_id}", _SEP]
    for p in d.get("predictions", [])[:10]:
        horizon = p.get("horizon_days", "?")
        archetype = p.get("archetype", "?")
        lines.append(f"  [{archetype}] horizon: {horizon}d  ·  risk: {p.get('primary_risk', '')[:80]}")
        lines.append(f"    refuted if: {p.get('falsification_condition', '')[:80]}")
        lines.append("")
    if total == 0:
        lines.append("  no open predictions — make decisions to start the forecast flywheel")
    return "\n".join(lines)


@mcp.tool(title="ACE Calibration")
async def ace_calibration(product_id: str = DEFAULT_PRODUCT) -> str:
    """Per-archetype calibration scores — how accurate ACE's predictions have been."""
    from core.engine.mcp.tools import ace_calibration as _fn

    d = await _fn(product_id=product_id)
    calibrations = d.get("calibrations", [])
    lines = [f"◈ ACE Calibration  ·  {len(calibrations)} archetype(s)  ·  {product_id}", _SEP]
    if not calibrations:
        lines.append(f"  {d.get('message', 'no data yet')}")
    for c in calibrations:
        bar = "█" * int(c.get("calibration_score", 0) * 10)
        lines.append(
            f"  {c.get('archetype', '?'):12s}  {c.get('discipline', '?'):15s}  "
            f"{bar:<10s} {c.get('calibration_score', 0):.2f}  (n={c.get('sample_count', 0)})"
        )
    return "\n".join(lines)


@mcp.tool(title="ACE Rollout")
async def ace_rollout(candidate: str, product_id: str = DEFAULT_PRODUCT) -> str:
    """Rollout planner — 3 decision paths from a candidate initiative with gap scores."""
    from core.engine.mcp.tools import ace_rollout as _fn

    d = await _fn(candidate=candidate, product_id=product_id)
    branches = d.get("branches", [])
    lines = [
        f"◈ ACE Rollout  ·  {len(branches)} branch{'es' if len(branches) != 1 else ''}  ·  {candidate[:60]}",
        _SEP,
    ]
    for i, b in enumerate(branches, 1):
        score = b.get("terminal_score", 0.0)
        bar = "█" * int(score * 10)
        lines.append(f"  Branch {i}  {bar:<10s} {score:.2f}")
        path = b.get("path", [])
        for step in path:
            lines.append(f"    → {step[:80]}")
        lines.append(f"    ⚠  {b.get('top_risk', '')[:80]}")
        lines.append("")
    if not branches:
        lines.append("  no branches generated")
    best = d.get("best_path", [])
    if best:
        lines.append(f"  Best path: {' → '.join(str(s)[:40] for s in best)}")
    return "\n".join(lines)


@mcp.tool(title="Fork Reasoning")
async def ace_fork_reasoning(
    run_id: str,
    checkpoint_seq: int = 1,
    product_id: str = DEFAULT_PRODUCT,
    with_capability_lens: bool = False,
) -> str:
    """Fork a logged reasoning run at a checkpoint — re-reason the tail under alternative lenses and
    compare, returning the best continuation before acting (may be the original). Set
    with_capability_lens to also weigh each branch's predicted capability trajectory (opt-in)."""
    from core.engine.mcp.tools import ace_fork_reasoning as _fn

    d = await _fn(
        run_id=run_id, checkpoint_seq=checkpoint_seq, product_id=product_id, with_capability_lens=with_capability_lens
    )
    if d.get("error"):
        return f"◈ Fork Reasoning  ·  {run_id}\n{_SEP}\n  ⚠  {d['error']}"
    forks = d.get("forks", [])
    best = d.get("best", {})
    orig = d.get("original", {})
    lines = [
        f"◈ Fork Reasoning  ·  {d.get('run_id', run_id)} @ seq {d.get('checkpoint_seq')}  ·  "
        f"{len(forks)} fork{'s' if len(forks) != 1 else ''}",
        _SEP,
        f"  Recommendation: {str(d.get('recommendation', '?')).upper()}",
        f"  Best: [{best.get('label', '?')}/{best.get('lens', '?')}]  score {float(best.get('score', 0.0)):.2f}",
        "",
        f"  original                {float(orig.get('score', 0.0)):.2f}",
    ]
    for i, f in enumerate(forks, 1):
        bar = "█" * int(float(f.get("score", 0.0)) * 10)
        lines.append(f"  fork {i} [{f.get('lens', '?')[:12]:<12s}] {bar:<10s} {float(f.get('score', 0.0)):.2f}")
    return "\n".join(lines)


@mcp.tool(title="Explain Run")
async def ace_explain_run(run_id: str = "", product_id: str = DEFAULT_PRODUCT) -> str:
    """Replay a reasoning run — 'why did ACE conclude this?'. No run_id → the most recent run."""
    from core.engine.mcp.tools import ace_explain_run as _fn

    d = await _fn(run_id=run_id, product_id=product_id)
    if not d.get("available"):
        return f"◈ Explain Run\n{_SEP}\n  ⚠  {d.get('error') or 'reasoning trace not available'}"
    phases = d.get("phases", [])
    lines = [
        f"◈ Why ACE concluded this  ·  {d.get('run_id', '')}  ·  {len(phases)} phase{'s' if len(phases) != 1 else ''}",
        _SEP,
        f"  thought: {(d.get('thought') or '')[:100]}",
        "",
    ]
    for p in phases:
        conf = p.get("confidence")
        conf_s = f"  ({float(conf):.2f})" if isinstance(conf, (int, float)) and not isinstance(conf, bool) else ""
        lines.append(f"  ● {p.get('function', '?')}{conf_s}")
        out = (p.get("output") or "")[:120]
        if out:
            lines.append(f"      {out}")
    concl = d.get("conclusion")
    if concl:
        lines.append("")
        lines.append(f"  → {str(concl)[:200]}")
    return "\n".join(lines)


@mcp.tool(title="Internal Signals")
async def ace_signals(
    product_id: str = DEFAULT_PRODUCT,
    kind: str | None = None,
    limit: int = 10,
) -> str:
    """List recent internal foresight signals for a product (capability_decline, gap_persistence, decision_velocity_drop). Signals are computed by the signal engine from ACE's own state — no external data sources."""
    from core.engine.mcp.tools import ace_signals as _fn

    d = await _fn(product_id=product_id, kind=kind, limit=limit)
    signals = d.get("signals", [])
    if not signals:
        return "No signals found."
    lines = [f"Signals ({len(signals)})", _SEP]
    for s in signals:
        conf = float(s.get("confidence", 0))
        lines.append(f"[{s.get('kind', '?')}] {s.get('description', '')}  (confidence: {conf:.2f})")
        lines.append(f"  subject: {s.get('subject', '')}  · id: {s.get('id', '')}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool(title="Foresight Scenario")
async def ace_scenario(
    signal_id: str,
    product_id: str = DEFAULT_PRODUCT,
) -> str:
    """Retrieve scenario branches projected for a given signal. Each branch includes a probability, description, product implication, and time horizon."""
    from core.engine.mcp.tools import ace_scenario as _fn

    d = await _fn(signal_id=signal_id, product_id=product_id)
    scenario = d.get("scenario")
    if not scenario:
        return f"No scenario found for signal {signal_id}."
    branches = scenario.get("branches", [])
    lines = [f"Scenario for {signal_id} [{scenario.get('kind', '?')}]", _SEP]
    for i, b in enumerate(branches, 1):
        prob = float(b.get("probability", 0))
        lines.append(f"Branch {i} ({prob:.0%}): {b.get('description', '')}")
        lines.append(f"  Implication: {b.get('implication_for_product', '')}")
        lines.append(f"  Horizon: {b.get('horizon', '')}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool(title="System Diagnostics")
async def ace_diagnostics(product_id: str = DEFAULT_PRODUCT) -> str:
    """Real-time health probes across every ACE subsystem: DB, worker, event bus, frameworks, sentinel, composition signals, conductor, and pending gates. Each probe runs with a 2-second timeout. Overall status: healthy / degraded / down."""
    from core.engine.mcp.tools import ace_diagnostics as _fn

    d = await _fn(product_id=product_id)
    status = d.get("status", "unknown")
    icon = {"healthy": "✓", "degraded": "⚠", "down": "✗"}.get(status, "○")
    probes = d.get("probes", {})
    failed = d.get("failed", [])

    lines = [f"{icon} ACE System Diagnostics  ·  {status.upper()}", _SEP]

    sections = {
        "Infrastructure": ["db", "worker", "llm"],
        "Intelligence": ["event_bus", "event_log", "frameworks"],
        "Product": ["insights", "conductor", "gates"],
        "Sentinel": ["sentinel"],
        "Composition": ["composition"],
    }

    for section, keys in sections.items():
        lines.append(f"\n{section}")
        for k in keys:
            p = probes.get(k, {})
            ok = p.get("ok", True)
            tick = "✓" if ok else "✗"
            detail = ""
            if k == "db":
                detail = "connected"
            elif k == "worker":
                detail = f"{p.get('latency_ms', '?')}ms" if ok else p.get("error", "unreachable")
            elif k == "llm":
                detail = "ready"
            elif k == "event_bus":
                detail = f"{p.get('emit_count', 0)} events  ·  {p.get('handlers', 0)} handlers"
            elif k == "event_log":
                detail = f"{p.get('count', 0)} entries"
            elif k == "frameworks":
                detail = f"{p.get('count', 0)} loaded"
            elif k == "insights":
                detail = f"{p.get('active', 0)} active"
            elif k == "conductor":
                detail = f"{p.get('active_tracks', 0)} tracks"
            elif k == "gates":
                detail = f"{p.get('pending', 0)} pending"
            elif k == "sentinel":
                detail = f"{p.get('recent_runs', 0)} recent runs"
            elif k == "composition":
                warm = p.get("warm_disciplines", 0)
                cold = p.get("cold_disciplines", 0)
                total = p.get("total_signals", 0)
                detail = f"{total} signals  ·  {warm} warm  ·  {cold} cold"
            if not ok:
                detail = p.get("error", "failed")
            lines.append(f"  {tick}  {k:<14}  {detail}")

    if failed:
        lines.append(f"\n{len(failed)} probe(s) failed: {', '.join(failed)}")

    return "\n".join(lines)


@mcp.tool(title="Architecture Diagram")
async def ace_diagram(
    scope: str = "system",
    product_id: str = DEFAULT_PRODUCT,
) -> str:
    """Generate a Mermaid architecture diagram from the code graph.

    Returns a C4-style flowchart curated by the LLM abstraction pass. The
    diagram groups capabilities into containers by package, infers relationships,
    and annotates technology tags. If the LLM is unavailable, a degraded diagram
    is returned with a warning.
    """
    from core.engine.mcp.tools import ace_diagram as _fn

    d = await _fn(scope=scope, product_id=product_id)
    if "error" in d:
        return f"✗ ace_diagram error: {d['error']}"

    mermaid = d.get("mermaid", "")
    lines = [f"◈ Architecture Diagram  ·  {product_id}  ·  scope={scope}", _SEP]
    if d.get("degraded"):
        lines.append("⚠ Degraded — LLM abstractor fell back to raw graph grouping")
        lines.append("")
    lines.append("```mermaid")
    lines.append(mermaid)
    lines.append("```")
    return "\n".join(lines)


@mcp.tool(title="Verify Implementation")
async def ace_verify_implementation(topic: str, product_id: str = DEFAULT_PRODUCT) -> dict:
    """Verify what's actually implemented for a topic by querying the code graph.

    Use before making any claim about what exists or doesn't exist.
    Returns ground-truth evidence from graph_file, graph_function, and graph_decision.
    Verdict: 'implemented' | 'partial' | 'not_found'.
    """
    from core.engine.mcp.tools import ace_verify_implementation as _fn

    return await _fn(topic=topic, product_id=product_id)


@mcp.tool(title="Test Coverage")
async def ace_test_coverage(
    repo_path: str = ".",
    stack: str | None = None,
    persist: bool = True,
) -> dict:
    """Run test coverage and persist results to capability_coverage.

    Runs pytest --cov for Python (stack-appropriate tool for others). Binds file
    coverage to capabilities via realizes edges. Persists current state, snapshot history,
    and capability_finding rows for untested functions. Returns per-capability coverage
    ranked by gap, plus summary stats.
    """
    from core.engine.mcp.tools import ace_test_coverage as _fn

    return await _fn(repo_path=repo_path, stack=stack, persist=persist)


@mcp.tool(title="Test Gaps")
async def ace_test_gaps(
    capability_slug: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> dict:
    """Query persisted test-gap findings and ranked capability list.

    Shows which capabilities have the worst test coverage and which specific
    functions are untested. Use with ace_generate_tests(mode='priority') to
    close the highest-impact gaps first.
    """
    from core.engine.mcp.tools import ace_test_gaps as _fn

    return await _fn(capability_slug=capability_slug, severity=severity, limit=limit)


# ─── Ambition + Phase + Pillar tools (spec v1.2 — phase-aware substrate) ──────


@mcp.tool(title="Ambition")
async def ace_ambition(product_id: str = DEFAULT_PRODUCT) -> dict:
    """Return the current ambition snapshot — phase, demo target, target date."""
    from core.engine.mcp.tools import ace_ambition as _fn

    return await _fn(product_id=product_id)


@mcp.tool(title="Set Phase")
async def ace_set_phase(product_id: str, phase: str, reason: str) -> dict:
    """Set product phase explicitly. reason is required for the audit trail.

    phase ∈ {discovery, poc, alpha, beta, ga, mature}.
    """
    from core.engine.mcp.tools import ace_set_phase as _fn

    return await _fn(product_id=product_id, phase=phase, reason=reason)


@mcp.tool(title="Set Product Type")
async def ace_set_product_type(product_id: str, product_type: str) -> dict:
    """Set product_type. Affects floor-curve modifiers (ai_native | trading_system | dev_tool | ...)."""
    from core.engine.mcp.tools import ace_set_product_type as _fn

    return await _fn(product_id=product_id, product_type=product_type)


@mcp.tool(title="Set Product Scale")
async def ace_set_product_scale(product_id: str, scale: str) -> dict:
    """Set product_scale. Affects floor-curve modifiers (atomic | component | application | platform | enterprise)."""
    from core.engine.mcp.tools import ace_set_product_scale as _fn

    return await _fn(product_id=product_id, scale=scale)


@mcp.tool(title="Pillar Status")
async def ace_pillar_status(product_id: str = DEFAULT_PRODUCT) -> dict:
    """Return all 7 pillar scores (experience, interface, logic, state, operations, evolution, trust)."""
    from core.engine.mcp.tools import ace_pillar_status as _fn

    return await _fn(product_id=product_id)


@mcp.tool(title="Phase Status")
async def ace_phase_status(product_id: str = DEFAULT_PRODUCT) -> dict:
    """Return current phase, days-in-phase, and pillars below their floor (blockers to advance)."""
    from core.engine.mcp.tools import ace_phase_status as _fn

    return await _fn(product_id=product_id)


@mcp.tool(title="Query Uncertainty")
async def ace_query_uncertainty(product_id: str, scope: str, question: str, fallback_action: str) -> dict:
    """Raise an uncertainty query rather than silently defaulting. Surfaces to the Proactive Line.

    scope ∈ {state, ambition, contributors, learnings}.
    fallback_action ∈ {pause, proceed_with_assumption, dispatch_research, default_safe}.
    """
    from core.engine.mcp.tools import ace_query_uncertainty as _fn

    return await _fn(
        product_id=product_id,
        scope=scope,
        question=question,
        fallback_action=fallback_action,
    )


@mcp.tool(title="Acknowledge Recommendation")
async def ace_acknowledge_recommendation(rec_id: str) -> dict:
    """Acknowledge a recommendation — resets its briefing-count and decay multiplier."""
    from core.engine.mcp.tools import ace_acknowledge_recommendation as _fn

    return await _fn(rec_id=rec_id)


@mcp.tool(title="Suggest Phase")
async def ace_suggest_phase(product_id: str = DEFAULT_PRODUCT) -> dict:
    """Suggest a phase from observable state (capability count + completion rate). Manual override stays."""
    from core.engine.mcp.tools import ace_suggest_phase as _fn

    return await _fn(product_id=product_id)


@mcp.tool(title="Briefing Payload")
async def ace_briefing_payload(product_id: str = DEFAULT_PRODUCT) -> dict:
    """Return the structured BriefingPayload (phase-aware substrate contract).

    Distinct from ace_briefing (markdown text for humans). Data contract surface:
    current_phase, phase_floors, pillar_scores, top_recommendations,
    blocked_patterns, open uncertainty queries.
    """
    from core.engine.mcp.tools import ace_briefing_payload as _fn

    return await _fn(product_id=product_id)


@mcp.tool(title="ACE journey count")
async def ace_journey_count(product: str = DEFAULT_PRODUCT, since: str = "week") -> dict:
    """Return the count of journey events for a product within a time window.

    Used by the SessionStart hook footer to show 'N events this week' tease.
    `since` ∈ {day, week, month}.
    """
    from core.engine.mcp.tools import ace_journey_count as _fn

    return await _fn(product=product, since=since)


@mcp.tool(title="ACE voice audit summary")
async def ace_voice_audit_summary(product: str = DEFAULT_PRODUCT) -> dict:
    """Return latest voice audit summary {overall_score, surface_count, violations_count}.

    Used by the SessionStart hook footer for the voice teaser line.
    """
    from core.engine.mcp.tools import ace_voice_audit_summary as _fn

    return await _fn(product=product)


@mcp.tool(title="Inspect Relationship Assertion")
async def ace_assertion(assertion_id: str) -> dict:
    """Explain one assertion: evidence, proposers, reviews, lifecycle, and operational projection."""
    from core.engine.graph.assertions import inspect_assertion

    result = await inspect_assertion(assertion_id)
    return result or {"error": "assertion_not_found", "assertion_id": assertion_id}


_flavor_tools_registered = False


def _register_flavor_tools() -> None:
    """Register flavor-contributed MCP tools onto the server. Idempotent.

    MCP clients introspect the tool list at connect time, so flavor tools must be
    registered eagerly (they can't be lazy like instruments/recipes). Reading
    registered_tools() triggers flavor loading via the shared load-once guard.
    """
    global _flavor_tools_registered
    if _flavor_tools_registered:
        return
    _flavor_tools_registered = True
    from core.engine.extensions.registry import registered_tools

    for tool in registered_tools():
        mcp.tool(tool["fn"], title=tool["title"])


@mcp.tool(title="Forget")
async def ace_forget(
    insight_id: str,
    reason: str,
    confirm: bool = False,
    product_id: str = "product:default",
) -> str:
    """Erase one insight by id (right-to-erasure). DRY-RUN by default — shows what would be erased; pass confirm=true to actually erase (irreversible). `reason` is required and recorded in an append-only audit log. Single-target only; never bulk."""
    from core.engine.mcp.tools import ace_forget as _forget

    d = await _forget(
        insight_id=insight_id,
        reason=reason,
        actor="mcp",
        confirm=confirm,
        product_id=product_id,
    )
    if d.get("erased"):
        return (
            f"🗑️  Erased {insight_id}  ·  {d.get('edges_removed', 0)} edge(s)  ·  audit hash {d.get('content_hash', '')}"
        )
    if d.get("would_erase"):
        return (
            f"⚠️  DRY-RUN — would erase {insight_id}  ·  {d.get('edges', 0)} edge(s)\n"
            f"{d.get('content_preview', '')}\n→ re-call with confirm=true to erase (irreversible)"
        )
    return f"· nothing erased: {d.get('reason', 'not found')}"


@mcp.tool(title="Forget by Hash")
async def ace_forget_by_hash(
    content_hash: str,
    reason: str,
    confirm: bool = False,
    product_id: str = "product:default",
) -> str:
    """Erase every insight whose content matches a hash (forget a fact everywhere). DRY-RUN by default; confirm=true to erase. `reason` required, audited."""
    from core.engine.mcp.tools import ace_forget_by_hash as _forget_hash

    d = await _forget_hash(
        content_hash=content_hash,
        reason=reason,
        actor="mcp",
        confirm=confirm,
        product_id=product_id,
    )
    if "erased_count" in d:
        return f"🗑️  Erased {d['erased_count']} insight(s) matching hash {content_hash}"
    return f"⚠️  DRY-RUN — would erase {d.get('would_erase_count', 0)} insight(s) matching {content_hash}\n→ confirm=true to erase"


# Register at import time so the flavor tool surface is present regardless of how
# the server is started (ace-mcp script, ASGI mount, or test import).
_register_flavor_tools()


def main():
    """Entry point for ace-mcp script."""
    mcp.run()


if __name__ == "__main__":
    main()
