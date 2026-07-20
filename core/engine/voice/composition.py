"""Composition primitives — assemble rendered voice strings into briefing sections."""

from __future__ import annotations

from core.engine.voice.renderers import render_recommendation, render_uncertainty


def lede_paragraph(frame_str: str, drift_str: str) -> str:
    """Join frame + drift into one paragraph. Drops drift if empty."""
    if not drift_str:
        return frame_str
    return f"{frame_str} {drift_str}"


def focus_section(top_recs: list[dict], n: int = 3) -> str:
    """Render top-N recommendations as a Markdown bulleted section."""
    bullets = []
    for rec in top_recs[:n]:
        body = render_recommendation(rec)
        bullets.append(f"- {body}")
    return "## Focus this week\n\n" + "\n".join(bullets)


def open_questions_section(qs: list[dict]) -> str | None:
    """Render open uncertainty queries. Returns None when qs is empty (drops section)."""
    if not qs:
        return None
    bullets = [f"- {render_uncertainty(q)}" for q in qs]
    return "## Open questions\n\n" + "\n".join(bullets)


def engine_footer(engine_runs: list[dict] | None) -> str:
    """Build the collapsed <details> footer summarizing engine activity."""
    if not engine_runs:
        body = "(No engine activity in this window.)"
    else:
        from core.engine.sentinel.engines.briefing import aggregate_engine_results

        metrics = aggregate_engine_results(engine_runs)
        body = (
            f"Collapsed: {metrics['engine_runs_summarized']} engines summarized — "
            f"{metrics['corrections_written']} corrections written, "
            f"{metrics['gaps_filled']} gaps filled, "
            f"{metrics['insights_verified']} insights verified, "
            f"{metrics.get('conflicts_found', 0)} contradictions surfaced."
        )
    return f"<details>\n<summary>Engine activity from this week ▸</summary>\n\n{body}\n\n</details>"
