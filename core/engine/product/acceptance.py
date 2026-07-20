"""Acceptance Verifier — verify agent work against the original spec.

Closes the loop: gap → spec → agent builds → acceptance verifies → gap closed (or follow-up).

Verification V2 adds:
- Behavioral evidence (code inspection, test execution, integration validation) before LLM judgment
- Pre-commitment protocol (evaluator commits to a preliminary verdict before seeing evidence)
- Honesty enforcement (test failures are a hard gate on "met" verdicts)
"""

import logging

from core.engine.core.db import parse_one, parse_rows
from core.engine.core.llm import get_llm
from core.engine.product.map import ProductMap
from core.engine.verification import run_checks
from core.engine.verification.models import format_evidence

logger = logging.getLogger(__name__)


class AcceptanceVerifier:
    """Verify agent work against the original spec."""

    def __init__(self, db_pool):
        self._pool = db_pool
        self._product_map = ProductMap(db_pool)
        self._llm = get_llm()

    async def verify(self, spec_id: str, product_id: str) -> dict:
        """Verify a completed spec against its acceptance criteria.

        1. Load the spec and its acceptance criteria
        2. Run behavioral checks (code inspection, tests, integration)
        3. For each criterion, evaluate with evidence via LLM
        4. Apply honesty enforcement (test failures block "met" verdicts)
        5. If capability linked, re-check quality score
        6. Return VerificationResult-compatible dict
        7. Update spec status based on result
        """
        async with self._pool.connection() as db:
            # Load spec
            spec_result = await db.query(
                "SELECT * FROM <record>$spec_id",
                {"spec_id": spec_id},
            )
            spec = parse_one(spec_result)
            if not spec:
                return {"error": f"Spec '{spec_id}' not found"}

            criteria = spec.get("acceptance_criteria", [])
            if not criteria:
                return {"error": "Spec has no acceptance criteria"}

            # ── Behavioral checks (V2) ──────────────────────────
            behavioral_evidence = {}
            try:
                behavioral_evidence = await run_checks(spec)
            except Exception as exc:
                logger.warning("Behavioral checks failed (proceeding without): %s", exc)

            # ── Honesty enforcement (V2) ────────────────────────
            honesty = None
            try:
                from core.engine.verification.honesty import HonestyEnforcer, PreCommitmentProtocol

                honesty = {
                    "protocol": PreCommitmentProtocol(self._llm),
                    "enforcer": HonestyEnforcer(),
                }
            except Exception as exc:
                logger.debug("Honesty module not available (proceeding without): %s", exc)

            # Evaluate each criterion with evidence
            criteria_results = []
            for i, criterion in enumerate(criteria):
                c_text = criterion.get("criterion", criterion) if isinstance(criterion, dict) else str(criterion)

                # Get behavioral evidence for this criterion
                check_result = behavioral_evidence.get(i)
                evidence_list = check_result.evidence if check_result else []
                evidence_text = format_evidence(evidence_list)

                # ── Pre-commitment (V2) ─────────────────────────
                pre_commitment = None
                if honesty:
                    try:
                        pre_commitment = await honesty["protocol"].pre_commit(c_text, spec.get("objective", ""))
                    except Exception as exc:
                        logger.debug("Pre-commitment failed: %s", exc)

                # Build evidence-informed evaluation prompt
                pre_commitment_ctx = ""
                if pre_commitment:
                    pre_commitment_ctx = f"""
YOUR PRE-COMMITMENT (made before seeing evidence):
Preliminary verdict: {pre_commitment.preliminary}
Evidence you said you needed: {pre_commitment.evidence_needed}
If your final verdict differs from your preliminary, explain why.
"""

                eval_prompt = f"""Evaluate whether this acceptance criterion has been met.

SPEC OBJECTIVE: {spec.get("objective", "")}
CRITERION: {c_text}
FILES MODIFIED: {spec.get("estimated_files", [])}

BEHAVIORAL EVIDENCE (automated checks):
{evidence_text}
{pre_commitment_ctx}
Based on the spec context AND the behavioral evidence above, assess:
- Has this criterion been implemented?
- Does the behavioral evidence support or contradict your assessment?

Return JSON: {{"status": "met" or "not_met" or "unclear", "evidence": "explanation", "evidence_aligned": true or false}}"""

                try:
                    result = await self._llm.complete_json(eval_prompt)
                    if isinstance(result, dict):
                        verdict_status = result.get("status", "unclear")
                        evidence_aligned = result.get("evidence_aligned", True)
                    else:
                        verdict_status = "unclear"
                        evidence_aligned = True
                        result = {"evidence": "LLM returned invalid format"}
                except Exception as e:
                    verdict_status = "unclear"
                    evidence_aligned = True
                    result = {"evidence": str(e)}

                # ── Honesty enforcement (V2) ────────────────────
                enforced = None
                if honesty and evidence_list:
                    enforced = honesty["enforcer"].enforce(verdict_status, evidence_list)
                    verdict_status = enforced.status

                criteria_results.append(
                    {
                        "criterion": c_text,
                        "status": verdict_status,
                        "evidence": result.get("evidence", ""),
                        "evidence_aligned": evidence_aligned,
                        "behavioral_checks": len(evidence_list),
                        "enforced": enforced.enforced if enforced else False,
                        "flagged": enforced.flagged if enforced else False,
                    }
                )

                # ── Persist evidence + judgment (V2, best-effort) ──
                await self._persist_verification_data(
                    db,
                    spec_id,
                    product_id,
                    i,
                    evidence_list,
                    pre_commitment,
                    verdict_status,
                    evidence_aligned,
                    enforced,
                )

            # Determine overall result
            met_count = sum(1 for r in criteria_results if r["status"] == "met")
            total = len(criteria_results)

            if met_count == total:
                overall = "fully_met"
            elif met_count > 0:
                overall = "partially_met"
            else:
                overall = "not_met"

            # ── Persist verification signal (V2, best-effort) ──
            checks_run = sum(r.get("behavioral_checks", 0) for r in criteria_results)
            checks_passed = (
                sum(1 for cr in behavioral_evidence.values() for e in cr.evidence if e.status == "passed")
                if behavioral_evidence
                else 0
            )
            checks_failed = (
                sum(1 for cr in behavioral_evidence.values() for e in cr.evidence if e.status == "failed")
                if behavioral_evidence
                else 0
            )
            all_aligned = all(r.get("evidence_aligned", True) for r in criteria_results)

            try:
                await db.query(
                    """CREATE verification_signal SET
                        spec_id = <record>$spec_id,
                        checks_run = $checks_run,
                        checks_passed = $checks_passed,
                        checks_failed = $checks_failed,
                        evidence_aligned = $aligned,
                        overall_verdict = $verdict""",
                    {
                        "product": product_id,
                        "spec_id": spec_id,
                        "checks_run": checks_run,
                        "checks_passed": checks_passed,
                        "checks_failed": checks_failed,
                        "aligned": all_aligned,
                        "verdict": overall,
                    },
                )
            except Exception:
                pass

            # Check quality delta if capability linked
            quality_delta = None
            cap_id = spec.get("capability")
            if cap_id:
                # Get current quality for this capability
                q_result = await db.query(
                    "SELECT dimension, score FROM capability_quality WHERE capability = <record>$cap_id",
                    {"cap_id": str(cap_id)},
                )
                quality_delta = {q["dimension"]: q["score"] for q in parse_rows(q_result)}

                # Create quality_delta edges: spec -> capability_quality (best-effort)
                try:
                    from core.engine.graph.edge_writer import create_edge

                    for q in parse_rows(q_result):
                        if q.get("id"):
                            await create_edge(
                                "quality_delta",
                                str(spec["id"]),
                                str(q["id"]),
                                metadata={
                                    "after_score": q.get("score"),
                                    "closed_gap": q.get("score", 0) >= 0.6,
                                },
                                pool=self._pool,
                            )
                except Exception:
                    pass

            # Update spec status
            new_status = "completed" if overall == "fully_met" else "failed"
            await db.query(
                "UPDATE <record>$spec_id SET status = $status, updated_at = time::now()",
                {"spec_id": spec_id, "status": new_status},
            )

            try:
                from core.engine.events.bus import bus

                await bus.emit(
                    "spec.verified",
                    {
                        "product_id": product_id,
                        "spec_id": spec_id,
                        "overall": overall,
                        "met": met_count,
                        "total": total,
                        "capability_id": str(spec.get("capability", "")) if spec.get("capability") else None,
                    },
                )
            except Exception:
                pass

            verification = {
                "spec_id": spec_id,
                "overall": overall,
                "criteria_results": criteria_results,
                "quality_delta": quality_delta,
                "follow_up_needed": overall != "fully_met",
                "met": met_count,
                "total": total,
                "behavioral_checks_run": checks_run,
                "behavioral_checks_passed": checks_passed,
                "behavioral_checks_failed": checks_failed,
            }

            # If partially met or not met, surface unmet criteria
            if overall != "fully_met":
                unmet = [r for r in criteria_results if r["status"] != "met"]
                verification["unmet_criteria"] = unmet

            return verification

    async def _persist_verification_data(
        self,
        db,
        spec_id: str,
        product_id: str,
        criterion_index: int,
        evidence_list: list,
        pre_commitment,
        final_verdict: str,
        evidence_aligned: bool,
        enforced,
    ) -> None:
        """Persist behavioral evidence and evaluator judgment (best-effort)."""
        try:
            # Persist each evidence record
            for e in evidence_list:
                await db.query(
                    """CREATE verification_evidence SET
                        spec_id = <record>$spec_id,
                        criterion_index = $idx,
                        check_type = $check_type,
                        status = $status,
                        details = $details,
                        duration_ms = $duration_ms""",
                    {
                        "product": product_id,
                        "spec_id": spec_id,
                        "idx": criterion_index,
                        "check_type": e.check_type,
                        "status": e.status,
                        "details": e.details,
                        "duration_ms": e.duration_ms,
                    },
                )

            # Persist evaluator judgment (if honesty module active)
            if pre_commitment is not None:
                flipped = (pre_commitment.preliminary == "likely_not_met" and final_verdict == "met") or (
                    pre_commitment.preliminary == "likely_met" and final_verdict == "not_met"
                )

                evidence_summary = {}
                for e in evidence_list:
                    evidence_summary[e.check_type] = e.status

                await db.query(
                    """CREATE evaluator_judgment SET
                        spec_id = <record>$spec_id,
                        criterion_index = $idx,
                        pre_commitment = $pre,
                        final_verdict = $verdict,
                        flipped = $flipped,
                        evidence_aligned = $aligned,
                        overridden = $overridden,
                        override_reason = $override_reason,
                        behavioral_evidence_summary = $summary""",
                    {
                        "product": product_id,
                        "spec_id": spec_id,
                        "idx": criterion_index,
                        "pre": pre_commitment.preliminary,
                        "verdict": final_verdict,
                        "flipped": flipped,
                        "aligned": evidence_aligned,
                        "overridden": enforced.enforced if enforced else False,
                        "override_reason": enforced.reason if enforced and enforced.enforced else None,
                        "summary": evidence_summary,
                    },
                )
        except Exception as exc:
            logger.debug("Failed to persist verification data: %s", exc)

    async def verify_gap_closed(self, dimension: str, capability_slug: str, product_id: str) -> dict:
        """Quick check: did the quality score improve for this dimension?

        Returns {closed: bool, score: float, threshold: float}
        """
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT score, assessed_at FROM capability_quality
                   WHERE product = <record>$product
                   AND dimension = <string>$dim
                   AND capability.slug = <string>$slug
                   ORDER BY assessed_at DESC LIMIT 1""",
                {"product": product_id, "dim": dimension, "slug": capability_slug},
            )
            current = parse_one(result)

            if not current:
                return {"closed": False, "before": 0, "after": 0, "delta": 0}

            score = current.get("score", 0)
            # Consider gap "closed" if score >= 0.6
            return {
                "closed": score >= 0.6,
                "score": score,
                "threshold": 0.6,
            }
