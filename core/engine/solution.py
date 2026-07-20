"""The Solution — the unit of work the engine produces and the arms build.

A living object: the intent (the vision) + the reasoning/path + connections +
foresight + the build plan + outcome. Plan 1 keeps it in memory; graph
persistence (the active loop for actions) lands with the execution layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Solution:
    intent: str  # the vision, in plain language
    reasoning: str = ""  # the committee's path to the solution
    connections: list[dict] = field(default_factory=list)  # graph neighbors / tensions
    foresight: list[dict] = field(default_factory=list)  # predicted consequences
    plan: Any = None  # the ActionPlan the arm produced
    outcome: Any = None  # the ArmResult + verdict
    # open | planned | built | verified | failed | parked
    #   failed = the work was wrong (reversible, discarded, repairable)
    #   parked = the environment broke before we could find out (workspace PRESERVED, needs a human)
    status: str = "open"
    domain_hint: str | None = None  # routing hint (e.g. "code")
    spec_id: str | None = None  # the agent_spec this Solution builds (Phase 3.2)
    product_id: str = "product:platform"  # the product this work is scoped to (set by dispatch)
    run_id: str | None = None  # the arm_run this build is ledgered under (set by dispatch)
