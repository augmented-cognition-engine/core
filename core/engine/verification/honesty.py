# engine/verification/honesty.py
"""Evaluator honesty enforcement — anti-sycophancy for acceptance verification.

Two mechanisms:
1. Pre-commitment protocol: evaluator commits to a preliminary verdict before seeing evidence
2. Evidence threshold enforcement: test failures are a hard gate on "met" verdicts

The key insight from Anthropic's harness design article: evaluators "identify issues
but rationalize approving anyway." Pre-commitment creates a cognitive anchor that makes
flips visible and trackable. Evidence enforcement prevents the most egregious cases.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.llm import LLMProvider
from core.engine.verification.models import BehavioralEvidence, EnforcedVerdict, PreCommitment

logger = logging.getLogger(__name__)


class PreCommitmentProtocol:
    """Force evaluator to commit to a verdict before seeing evidence.

    Call 1 (pre_commit): LLM sees ONLY criterion + objective. No evidence.
    Call 2 (judge_with_evidence): LLM sees its pre-commitment AND the evidence.

    If Call 2 flips from likely_not_met to met, the flip is tracked.
    Uses budget model for Call 1 (prompt is short, doesn't need full capability).
    """

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def pre_commit(self, criterion: str, objective: str) -> PreCommitment:
        """Call 1: commit to preliminary verdict without evidence."""
        prompt = f"""You are evaluating whether work meets an acceptance criterion.
You have NOT yet seen any evidence of the implementation.
Based only on the criterion and objective, state your preliminary assessment
and what evidence you would need to confirm.

OBJECTIVE: {objective}
CRITERION: {criterion}

Return JSON: {{"preliminary": "likely_met" or "likely_not_met" or "uncertain", "evidence_needed": "what would confirm this"}}"""

        try:
            result = await self._llm.complete_json(prompt, model=settings.llm_budget_model)
            if isinstance(result, dict):
                preliminary = result.get("preliminary", "uncertain")
                if preliminary not in ("likely_met", "likely_not_met", "uncertain"):
                    preliminary = "uncertain"
                return PreCommitment(
                    preliminary=preliminary,
                    evidence_needed=result.get("evidence_needed", ""),
                )
        except Exception as exc:
            logger.debug("Pre-commitment LLM call failed: %s", exc)

        return PreCommitment(preliminary="uncertain", evidence_needed="")


class HonestyEnforcer:
    """Enforce evidence-based verdicts on acceptance criteria.

    Hard gate: if test_execution checks failed, the criterion CANNOT be "met"
    unless explicitly overridden (and the override is tracked).

    Soft flag: if code_inspection checks failed, the criterion is flagged
    but allowed — functions may have been renamed/moved.
    """

    def enforce(
        self,
        proposed_verdict: str,
        evidence: list[BehavioralEvidence],
    ) -> EnforcedVerdict:
        """Apply honesty enforcement to a proposed verdict.

        Returns EnforcedVerdict with:
        - status: the final verdict (may differ from proposed)
        - enforced: True if the enforcer overrode the verdict
        - flagged: True if soft evidence contradicts but verdict is allowed
        - reason: explanation of why the enforcer intervened
        """
        if not evidence:
            return EnforcedVerdict(status=proposed_verdict)

        # Hard gate: test execution failures
        test_failures = [e for e in evidence if e.status == "failed" and e.check_type == "test_execution"]
        if proposed_verdict == "met" and test_failures:
            failed_count = len(test_failures)
            # Aggregate test failure details
            total_failed = sum(e.details.get("tests_failed", 0) for e in test_failures)
            reason = f"{failed_count} test execution check(s) failed ({total_failed} test(s) failed)"
            return EnforcedVerdict(
                status="not_met",
                enforced=True,
                reason=reason,
            )

        # Soft flag: code inspection failures
        code_failures = [e for e in evidence if e.status == "failed" and e.check_type == "code_inspection"]
        if proposed_verdict == "met" and code_failures:
            missing = []
            for e in code_failures:
                missing.extend(e.details.get("functions_missing", []))
            reason = f"Code inspection found missing: {missing}" if missing else "Code inspection check(s) failed"
            return EnforcedVerdict(
                status=proposed_verdict,  # allow but flag
                flagged=True,
                reason=reason,
            )

        # Integration validation failures — soft flag
        integration_failures = [
            e for e in evidence if e.status == "failed" and e.check_type == "integration_validation"
        ]
        if proposed_verdict == "met" and integration_failures:
            return EnforcedVerdict(
                status=proposed_verdict,
                flagged=True,
                reason="Integration validation check(s) failed",
            )

        return EnforcedVerdict(status=proposed_verdict)
