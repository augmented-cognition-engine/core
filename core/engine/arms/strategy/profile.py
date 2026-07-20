"""WorkProfile — the graph-grounded, conversational, overridable depth decision."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkProfile:
    scope: str = "nearby"  # none | nearby | module | repo
    novelty: str = "modify"  # greenfield | extend | modify | fix
    risk: str = "connected"  # isolated | connected | systemic
    verify_depth: str = "unit"  # smoke | unit | full
    task_type: str = "change"  # human label, derived
