"""The roadmap collaborators read — GENERATED, because a hand-written one is a lying instrument.

The repo carries four hand-maintained roadmaps (ace-roadmap, ace-master-roadmap, a dated "refresh",
and a "world-class" one). Four roadmaps is no roadmap: a collaborator cannot tell which is real, and
every one began rotting the moment the next commit landed.

This is not a theoretical worry. The DATABASE roadmap — the live one — had drifted so far that five
specs said "build this" while the thing sat in the repo with eleven test files. If the source of
truth drifts, a copy typed out by hand has no chance at all.

So: statuses come from the database. Areas come from a human-owned manifest (docs/roadmap/areas.yml),
because "which subsystem does this belong to" is a judgement a machine should not be making up. The
output says when it was generated and how to regenerate it, so nobody hand-edits a file that is
about to be overwritten.

And it never silently drops a spec. Anything that fits no area lands under "Unsorted", loudly, with
the capability that failed to match — because a roadmap that quietly omits work is the same lie in a
politer voice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# How a status reads to someone skimming. The point is that "shipped" and "someone is building this
# right now" and "waiting on a human" must not look the same — that ambiguity is what let five
# already-built specs sit in the backlog looking like work.
_STATUS = {
    "shipped": ("✅", "shipped"),
    "completed": ("✅", "shipped"),
    "built": ("🧪", "built — awaiting review"),
    "building": ("🔨", "in progress"),
    "executing": ("🔨", "in progress"),
    "verifying": ("🔍", "verifying"),
    "approved": ("🟢", "approved — queued to build"),
    "draft": ("📝", "draft — needs your approval"),
    "blocked": ("⛔", "blocked — needs a human"),
    "superseded": ("🗑", "superseded"),
    "failed": ("❌", "failed"),
}
_UNKNOWN = ("•", "unknown")

_HEADER = """# ACE Roadmap

> **GENERATED FILE — DO NOT EDIT BY HAND.**
> Statuses come from the live database; areas come from `docs/roadmap/areas.yml`.
> Regenerate with `make roadmap`. Anything you type here will be overwritten.
>
> Generated {stamp}

ACE is a reasoning engine. This is what is being built in it, grouped by subsystem, with the status
each item actually has — not the status someone remembered to write down.

"""

_FOOTER = """
---

### How to read this

| | |
|---|---|
| ✅ | shipped — it is in the codebase |
| 🧪 | built, awaiting human review |
| 🔨 | in progress right now |
| 🟢 | approved — the build loop will pick it up |
| 📝 | draft — waiting on a human to approve it |
| ⛔ | blocked — something needs a person |

**Want to help?** Anything marked 📝 or 🟢 is fair game. See `CONTRIBUTING.md`.

**Something look wrong?** It probably is. This file is generated from the spec database, and the
database can drift from the code — we found five specs claiming to need work that was already
built. If an item here is already done, say so; that is a real bug report.
"""


def _fmt_status(status: str | None) -> tuple[str, str]:
    return _STATUS.get((status or "").lower(), _UNKNOWN)


def _line(spec: dict[str, Any]) -> str:
    icon, label = _fmt_status(spec.get("status"))
    objective = (spec.get("objective") or "(no objective)").strip().replace("\n", " ")
    if len(objective) > 160:
        objective = objective[:157] + "..."
    return f"- {icon} **{objective}**  \n  _{label}_"


def _match_area(objective: str, areas: dict[str, dict[str, Any]]) -> str | None:
    """Which area does this objective read like? Best match by keyword count, ties broken by manifest
    order. A heuristic, and labelled as one — but a heuristic that a human can edit in a PR beats an
    "Unsorted" list containing the entire roadmap."""
    text = (objective or "").lower()
    best, best_score = None, 0
    for key, meta in areas.items():
        score = sum(1 for kw in (meta.get("match") or []) if str(kw).lower() in text)
        if score > best_score:
            best, best_score = key, score
    return best


def generate_roadmap(specs: list[dict[str, Any]], areas: dict[str, dict[str, Any]]) -> str:
    """Render the roadmap. Pure: no I/O, so it is testable and cannot fail on a network."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [_HEADER.format(stamp=stamp)]

    # Map capability -> area once. A capability listed under two areas is the manifest's problem,
    # and first-wins is a defensible, boring resolution.
    cap_to_area: dict[str, str] = {}
    for key, meta in areas.items():
        for cap in meta.get("capabilities") or []:
            cap_to_area.setdefault(str(cap), key)

    grouped: dict[str, list[dict]] = {k: [] for k in areas}
    unsorted: list[dict] = []
    for spec in specs or []:
        cap = spec.get("capability_slug")
        # The capability LINK is authoritative — it is data, not a guess.
        area = cap_to_area.get(str(cap)) if cap else None
        if area is None:
            # Fall back to keyword matching on the objective. Most specs carry no capability link
            # (36 of 37, measured), so without this the whole roadmap is one long "Unsorted" list —
            # honest, and completely useless to the collaborator it is written for. The rules live
            # in the manifest so they can be argued with in a pull request.
            area = _match_area(spec.get("objective") or "", areas)
        (grouped[area] if area else unsorted).append(spec)

    for key, meta in areas.items():
        out.append(f"## {meta.get('title', key)}\n")
        if meta.get("blurb"):
            out.append(f"{meta['blurb']}\n")
        items = grouped.get(key) or []
        if not items:
            if (meta.get("status") or "").lower() == "shipped":
                # A finished subsystem carries zero specs because it is DONE, not neglected — the
                # built voice-of-product engine, the live extensions, the roadmap tooling itself.
                # Rendering it the same as a genuine gap is the done-vs-empty lie this file exists to
                # kill. The manifest (human-owned) is where "this pillar is shipped" is asserted.
                out.append("_✅ Shipped and load-bearing — no tracked specs. Work here refines it; it is not a gap._\n")
            else:
                # Silence is ambiguous: "no voice work" and "we forgot voice exists" must not look alike.
                out.append("_No open work. (Nothing queued — not nothing to do.)_\n")
        else:
            # Shipped last: a reader wants to know what is LIVE and what is NEXT, in that order.
            live = [s for s in items if (s.get("status") or "") not in ("shipped", "completed", "superseded")]
            done = [s for s in items if (s.get("status") or "") in ("shipped", "completed")]
            for s in live:
                out.append(_line(s))
            if done:
                out.append(f"\n<details><summary>Shipped ({len(done)})</summary>\n")
                for s in done:
                    out.append(_line(s))
                out.append("\n</details>\n")
        out.append("")

    if unsorted:
        out.append("## Unsorted\n")
        out.append(
            "These specs match no area in `docs/roadmap/areas.yml`. They are shown rather than "
            "dropped — a roadmap that quietly omits work is the same lie in a politer voice. "
            "**Fix the manifest, not this file.**\n"
        )
        for s in unsorted:
            cap = s.get("capability_slug") or "(no capability)"
            out.append(f"{_line(s)}  \n  _unmatched capability: `{cap}`_")
        out.append("")

    out.append(_FOOTER)
    return "\n".join(out)
