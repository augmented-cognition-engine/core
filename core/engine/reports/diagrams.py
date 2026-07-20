# engine/reports/diagrams.py
"""DiagramGenerator — SVG heat map and Mermaid DSL for PDF reports."""

from __future__ import annotations

import html
import re

# Business impact weight per discipline (0–1). Higher = more critical.
_DISCIPLINE_IMPACT: dict[str, float] = {
    "deployment": 1.0,
    "security": 0.9,
    "business_logic": 0.85,
    "devops": 0.8,
    "data_modeling": 0.8,
    "architecture": 0.75,
    "integration": 0.75,
    "testing": 0.7,
    "performance": 0.7,
    "data": 0.75,
    "accessibility": 0.55,
    "error_handling": 0.65,
    "ux": 0.6,
    "observability": 0.6,
    "api_design": 0.55,
    "documentation": 0.5,
    "configuration": 0.5,
    "dependency_management": 0.5,
    "versioning": 0.45,
    "code_conventions": 0.4,
}
_DEFAULT_IMPACT = 0.5

# SVG plot area constants
_W, _H = 560, 320
_X0, _X1 = 60, 530  # plot left/right
_Y0, _Y1 = 20, 260  # plot top/bottom (top = high impact)
_MX = (_X0 + _X1) // 2  # 295
_MY = (_Y0 + _Y1) // 2  # 140


def _score_color(score: float) -> str:
    if score < 0.3:
        return "#f87171"
    if score < 0.55:
        return "#fbbf24"
    if score < 0.7:
        return "#a3e635"
    return "#34d399"


def _safe_id(text: str) -> str:
    """Turn arbitrary text into a valid Mermaid node ID."""
    return re.sub(r"[^a-zA-Z0-9]", "_", text).strip("_") or "node"


class DiagramGenerator:
    # ── Risk Heat Map ─────────────────────────────────────────────────

    def svg_risk_heatmap(self, health_by_discipline: list[dict]) -> str:
        """Return a standalone SVG scatter plot of disciplines by score vs impact."""
        lines: list[str] = [
            f'<svg viewBox="0 0 {_W} {_H}" xmlns="http://www.w3.org/2000/svg"'
            f' style="width:100%;font-family:Inter,system-ui,sans-serif;">',
        ]

        # Quadrant fills
        _qw1, _qw2 = _MX - _X0, _X1 - _MX
        _qh1, _qh2 = _MY - _Y0, _Y1 - _MY
        lines += [
            f'<rect x="{_X0}" y="{_Y0}" width="{_qw1}" height="{_qh1}" fill="rgba(248,113,113,0.06)" rx="2"/>',
            f'<rect x="{_MX}" y="{_Y0}" width="{_qw2}" height="{_qh1}" fill="rgba(251,191,36,0.05)" rx="2"/>',
            f'<rect x="{_X0}" y="{_MY}" width="{_qw1}" height="{_qh2}" fill="rgba(52,211,153,0.04)" rx="2"/>',
            f'<rect x="{_MX}" y="{_MY}" width="{_qw2}" height="{_qh2}" fill="rgba(52,211,153,0.06)" rx="2"/>',
        ]

        # Quadrant labels
        q_labels = [
            ((_X0 + _MX) // 2, _Y0 + 14, "HIGH RISK", "rgba(248,113,113,0.5)"),
            ((_MX + _X1) // 2, _Y0 + 14, "WATCH", "rgba(251,191,36,0.5)"),
            ((_X0 + _MX) // 2, _Y1 - 8, "STABLE", "rgba(52,211,153,0.4)"),
            ((_MX + _X1) // 2, _Y1 - 8, "STRONG", "rgba(52,211,153,0.6)"),
        ]
        for lx, ly, lt, lc in q_labels:
            lines.append(
                f'<text x="{lx}" y="{ly}" text-anchor="middle" fill="{lc}"'
                f' font-size="8" letter-spacing="0.1em" font-weight="600">{lt}</text>'
            )

        # Grid lines + axes
        lines += [
            f'<line x1="{_X0}" y1="{_MY}" x2="{_X1}" y2="{_MY}" stroke="rgba(255,255,255,0.12)" stroke-width="1" stroke-dasharray="4,3"/>',
            f'<line x1="{_MX}" y1="{_Y0}" x2="{_MX}" y2="{_Y1}" stroke="rgba(255,255,255,0.12)" stroke-width="1" stroke-dasharray="4,3"/>',
            f'<line x1="{_X0}" y1="{_Y1}" x2="{_X1}" y2="{_Y1}" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>',
            f'<line x1="{_X0}" y1="{_Y0}" x2="{_X0}" y2="{_Y1}" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>',
            f'<text x="{_X0 + 4}" y="{_Y1 + 13}" fill="#888" font-size="8" letter-spacing="0.06em">LOW COVERAGE</text>',
            f'<text x="{_X1 - 82}" y="{_Y1 + 13}" fill="#888" font-size="8" letter-spacing="0.06em">HIGH COVERAGE →</text>',
            f'<text x="18" y="{_MY}" fill="#888" font-size="8" letter-spacing="0.06em"'
            f' transform="rotate(-90,18,{_MY})">IMPACT →</text>',
        ]

        # Data points
        for d in health_by_discipline:
            discipline = str(d.get("discipline", ""))
            raw_score = d.get("avg_score", 0.5)
            try:
                score = max(0.0, min(1.0, float(raw_score if raw_score is not None else 0.5)))
            except (TypeError, ValueError):
                score = 0.5
            impact = _DISCIPLINE_IMPACT.get(discipline, _DEFAULT_IMPACT)

            cx = int(_X0 + score * (_X1 - _X0))
            cy = int(_Y1 - impact * (_Y1 - _Y0))
            color = _score_color(score)

            lines.append(
                f'<circle cx="{cx}" cy="{cy}" r="7" fill="{color}" opacity="0.88"'
                f' stroke="{color}" stroke-width="5" stroke-opacity="0.2"/>'
            )

            label = html.escape(discipline.replace("_", " "))
            pct = f"{int(score * 100)}%"
            # Place label right; flip left if near right edge
            if cx > _X1 - 95:
                lx, anchor = cx - 12, "end"
            else:
                lx, anchor = cx + 12, "start"
            lines += [
                f'<text x="{lx}" y="{cy - 2}" text-anchor="{anchor}" fill="{color}"'
                f' font-size="7.5" font-weight="600">{label}</text>',
                f'<text x="{lx}" y="{cy + 9}" text-anchor="{anchor}" fill="#888" font-size="7">{pct}</text>',
            ]

        lines.append("</svg>")
        return "\n".join(lines)

    # ── Architecture Map ──────────────────────────────────────────────

    def mermaid_architecture_map(self, capabilities: list[dict]) -> str:
        """Return a Mermaid LR flowchart DSL string, capabilities grouped by category."""
        if not capabilities:
            return "flowchart LR\n  A[No capabilities mapped]"

        groups: dict[str, list[tuple[str, str]]] = {}
        for cap in capabilities:
            cat = (cap.get("category") or "General").strip()
            slug = str(cap.get("slug") or "unknown")
            node_id = _safe_id(slug)
            label = slug.replace("_", " ").replace("-", " ").title().replace('"', "'")
            groups.setdefault(cat, []).append((node_id, label))

        lines = ["flowchart LR"]
        for group_name, nodes in groups.items():
            gid = _safe_id(group_name)
            safe_label = group_name.replace('"', "'")
            lines.append(f'  subgraph {gid}["{safe_label}"]')
            for node_id, label in nodes:
                lines.append(f'    {node_id}["{label}"]')
            lines.append("  end")

        return "\n".join(lines)

    # ── Capability Dependency Graph ───────────────────────────────────

    def mermaid_capability_graph(self, capabilities: list[dict]) -> str:
        """Return a Mermaid TD graph DSL string with dependency edges."""
        if not capabilities:
            return "graph TD\n  A[No capabilities mapped]"

        # Cap at 20 nodes to avoid layout explosion
        capped = capabilities[:20]

        slug_set = {str(c.get("slug", "")) for c in capped}
        lines = ["graph TD"]

        for cap in capped:
            slug = str(cap.get("slug", "unknown"))
            node_id = _safe_id(slug)
            label = slug.replace("_", " ").replace("-", " ").title().replace('"', "'")
            lines.append(f'  {node_id}["{label}"]')

        # Edges from depends_on
        for cap in capped:
            slug = str(cap.get("slug", "unknown"))
            src_id = _safe_id(slug)
            depends_on = cap.get("depends_on") or []
            if not isinstance(depends_on, list):
                continue
            for dep in depends_on:
                # dep is a record ID like "capability:some_slug" or just a slug string
                dep_slug = str(dep).split(":")[-1]
                if dep_slug in slug_set:
                    lines.append(f"  {_safe_id(dep_slug)} --> {src_id}")

        return "\n".join(lines)
