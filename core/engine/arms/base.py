"""The Arm contract — one shared core, N specialized hands.

An arm is thin: it specializes the domain reasoning + the action verbs (the hand)
and inherits everything else (committee, graph, verification) from the core.
Plan 1 defines the contract + dispatches it; execution is simulated until the
worktree execution layer (Plan 2) lands.
"""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from core.engine.solution import Solution

if TYPE_CHECKING:
    from core.engine.arms.execution.workspace import Workspace
    from core.engine.arms.strategy.profile import WorkProfile


def score_domain_match(solution: Solution, *, domain: str, terms: tuple[str, ...]) -> int:
    """Shared routing score (higher = more specific). An exact domain_hint wins outright;
    otherwise count WHOLE-WORD term hits in the intent. Whole-word (not substring) so
    'encoder'/'decode' don't match 'code' and a design spec mentioning 'code' as one word
    doesn't get out-scored by accident. route() picks the highest-scoring arm so a more
    specific arm isn't shadowed by an earlier-registered one that merely matches weakly."""
    if getattr(solution, "domain_hint", None) == domain:
        return 100
    intent = (solution.intent or "").lower()
    return sum(1 for t in terms if re.search(rf"\b{re.escape(t)}\b", intent))


class RiskTier(str, Enum):
    READ = "read"  # read/inspect — never gated
    REVERSIBLE = "reversible"  # write in an isolated workspace — proceeds, surfaced
    MUTATING = "mutating"  # merge/deploy/delete — ALWAYS gated for the human


class AutonomyTier(str, Enum):
    READ = "read"  # may auto-run read actions only
    REVERSIBLE = "reversible"  # may auto-run read + reversible actions
    NONE = "none"  # proposes only; nothing auto-runs


@dataclass
class Action:
    verb: str
    args: dict
    risk: RiskTier


@dataclass
class ActionPlan:
    summary: str
    actions: list[Action] = field(default_factory=list)
    test_cmd: list[str] | None = None  # scoped verify command (Code arm)
    surfaced_concerns: list[str] = field(default_factory=list)  # systems-thinking coverage items
    profile: "WorkProfile | dict | None" = None  # the depth profile this plan was built at (learning)
    pipeline: list[str] | None = None  # the assembled phase categories (learning)


@dataclass
class ArmResult:
    plan: ActionPlan
    performed: list[Action] = field(default_factory=list)
    simulated: bool = True
    logs: list[str] = field(default_factory=list)
    workspace: "Workspace | None" = None  # the execution workspace (Plan 2); None when simulated


@dataclass
class PromotionRequest:
    """A surfaced, un-performed MUTATING request — the human approves the merge."""

    branch: str
    diff_summary: str
    target: str = "master"


@dataclass
class Verdict:
    """The outcome of an attempt.

    passed=False means the WORK was wrong — reversible, discardable, repairable.
    parked=True means we never found out: the environment broke (model unreachable, DB down,
    disk full) or a gate could not run. Retrying is pointless and discarding the workspace
    destroys the evidence, so a parked run KEEPS its workspace and waits for a human. The
    diagnosis is what that human has to fix. Collapsing the two into "failed" is the lie that
    makes an unattended run un-reviewable.
    """

    passed: bool
    reason: str = ""
    parked: bool = False
    diagnosis: str = ""
    # WHO judged this: "arm" (the builder's own verify, which already ran its inner repair loop),
    # "critic" (the adversarial reviewer — a signal the arm has never seen and CAN still act on),
    # or "environment" (nothing judged it at all). repair() branches on this: re-fighting a battle
    # the inner loop already lost three times is a token furnace, not a repair.
    source: str = "arm"


class Arm(abc.ABC):
    """A domain brain + hand. Subclasses specialize; the core is inherited."""

    domain: str = "base"
    # What this arm actually BUILDS, in one line. The router shows these to the classifier, so an
    # arm that describes itself badly gets the wrong work — this string is load-bearing, not a
    # docstring. (Keyword lists could not carry this: _CODE_TERMS was literally ("code",), so a
    # spec had to say the word "code" to reach the code arm. 53% of the real backlog reached none.)
    description: str = ""
    autonomy: AutonomyTier = AutonomyTier.NONE
    # A GATE arm (e.g. the SHIP arm) assesses + surfaces concerns; it produces NO file-actions by design,
    # so dispatch must NOT treat its empty action list as "nothing to build" — it runs execute/verify and
    # honors the surfaced-concerns verdict. Producer arms (code/design/data) leave this False.
    is_gate: bool = False

    @abc.abstractmethod
    def can_handle(self, solution: Solution) -> bool: ...

    def match_score(self, solution: Solution) -> int:
        """Routing specificity — route() picks the highest-scoring arm (so a specific arm
        is not shadowed by an earlier-registered weak match). Default: 1 if can_handle else 0.
        Arms with overlapping vocabularies override to score by signal strength."""
        return 1 if self.can_handle(solution) else 0

    @abc.abstractmethod
    async def plan(self, solution: Solution) -> ActionPlan: ...

    @abc.abstractmethod
    async def execute(self, plan: ActionPlan) -> ArmResult: ...

    @abc.abstractmethod
    async def verify(self, result: ArmResult, plan: ActionPlan) -> Verdict: ...

    async def repair(self, result: ArmResult, plan: ActionPlan, verdict: Verdict) -> ActionPlan | None:
        """Given a FAILED verdict, produce a corrected plan — or None to accept the failure.

        This is what stops an arm's success rate from being its first-try rate. dispatch calls
        it (up to settings.arm_repair_budget times) with the failure reason, and re-runs
        execute → verify on whatever plan comes back.

        Default: None — an arm opts in by overriding. Arms that reason with an LLM should feed
        `verdict.reason` back as evidence rather than re-planning blind. NEVER called for a
        PARKED verdict: a dead environment does not heal by retrying.
        """
        return None
