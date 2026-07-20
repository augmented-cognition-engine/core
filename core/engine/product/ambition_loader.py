from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from core.engine.product.ambition import DemoTarget, Target

_PATTERN_HEADING = re.compile(r"^\s*###\s+\d+\.\s+([^\(]+?)(?:\s*\(|$)", re.MULTILINE)
_DEMO_NAME = re.compile(r"\*{0,2}demo\s+target:\*{0,2}\s*([^\n]+)", re.IGNORECASE)
_TARGET_DATE_ISO = re.compile(r"target date:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_TARGET_DATE_INLINE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b"
)
_SUCCESS_FN = re.compile(r"success function:\s*([^\n.]+)", re.IGNORECASE)
_HORIZON = re.compile(r"horizon:\s*(\d+)\s*days?", re.IGNORECASE)

_MONTH_MAP = {
    m: i
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        1,
    )
}


# Spec headings that have drifted from their canonical DB slug.
# Maps heading-derived slug → seed_partnership_patterns.py slug.
_SLUG_OVERRIDES: dict[str, str] = {
    "framework_tiles": "living_canvas",
    "reasoning_panel": "side_by_side_consultation_panel",
    "forward_momentum_panel": "continuous_thread",
    "briefing_panel": "briefing_as_permanent_artifact",
    "time_travel": "time_travel_by_default",
    "canvas_history_peek": "background_work_peek",
    "annotation_driven_tile_editing": "annotation_driven_editing",
}


def _normalize_pattern_name(name: str) -> str:
    """Normalize a spec heading to a canonical slug.

    Word separators (space, dash, slash) all become underscore — preserves
    semantic structure of compound names like "Quiet/Loud Mode" → quiet_loud_mode.
    Stripping punctuation only removes truly nonsemantic chars (quotes, periods).
    """
    n = name.strip().lower()
    n = re.sub(r"[\s\-/]+", "_", n)
    n = re.sub(r"[^a-z0-9_]", "", n)
    return _SLUG_OVERRIDES.get(n, n)


def extract_required_patterns(body: str) -> list[str]:
    matches = _PATTERN_HEADING.findall(body)
    return [_normalize_pattern_name(m) for m in matches if m.strip()]


def _parse_date_from_line(line: str) -> Optional[date]:
    iso = _TARGET_DATE_ISO.search(line)
    if iso:
        return date.fromisoformat(iso.group(1))
    natural = _TARGET_DATE_INLINE.search(line)
    if natural:
        return date(int(natural.group(3)), _MONTH_MAP[natural.group(1)], int(natural.group(2)))
    return None


def extract_demo_target(body: str) -> Optional[DemoTarget]:
    name_match = _DEMO_NAME.search(body)
    if not name_match:
        return None
    # Prefer date found on the demo line itself; fall back to a dedicated "Target date:" ISO line
    parsed_date = _parse_date_from_line(name_match.group(0)) or (
        _TARGET_DATE_ISO.search(body) and date.fromisoformat(_TARGET_DATE_ISO.search(body).group(1))
    )
    if not parsed_date:
        return None
    return DemoTarget(
        name=name_match.group(1).strip().lstrip("*").strip(),
        target_date=parsed_date,
        required_patterns=[],
        acceptance_criteria=[],
    )


def extract_success_function(body: str) -> str:
    m = _SUCCESS_FN.search(body)
    return m.group(1).strip() if m else ""


def extract_horizon_days(body: str) -> int:
    m = _HORIZON.search(body)
    return int(m.group(1)) if m else 0


def load_ambition_from_markdown(
    thesis_path: str,
    roadmap_path: str,
    ux_spec_path: str,
) -> Target:
    thesis_body = Path(thesis_path).read_text(encoding="utf-8") if Path(thesis_path).exists() else ""
    roadmap_body = Path(roadmap_path).read_text(encoding="utf-8") if Path(roadmap_path).exists() else ""
    ux_body = Path(ux_spec_path).read_text(encoding="utf-8") if Path(ux_spec_path).exists() else ""

    demo = extract_demo_target(thesis_body) or extract_demo_target(roadmap_body)
    if demo is not None:
        demo.required_patterns = extract_required_patterns(ux_body)

    return Target(
        thesis_ref=thesis_path,
        roadmap_ref=roadmap_path,
        demo_target=demo,
        success_function=extract_success_function(thesis_body),
        horizon_days=extract_horizon_days(roadmap_body),
    )
