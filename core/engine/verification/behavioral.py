# engine/verification/behavioral.py
"""Behavioral Check Runner — orchestrate check strategies based on spec metadata.

Selection logic is spec-driven, not hardcoded:
- Code inspection: always, if there are files to check
- Test execution: only for automated criteria with test paths
- Integration validation: only when integration_points exist

Evidence is collected per-criterion and returned as a dict[int, CheckResult].
"""

from __future__ import annotations

import logging

from core.engine.verification.checks.code_inspection import run_code_inspection
from core.engine.verification.checks.execution_check import run_test_execution
from core.engine.verification.checks.integration import run_integration_validation
from core.engine.verification.models import BehavioralEvidence, CheckResult

logger = logging.getLogger(__name__)


async def run_checks(
    spec: dict,
    project_root: str | None = None,
) -> dict[int, CheckResult]:
    """Run all applicable behavioral checks for a spec.

    Returns a dict mapping criterion_index -> CheckResult.
    Checks are selected based on spec metadata (automated flags,
    test_requirements, integration_points).
    """
    criteria = spec.get("acceptance_criteria", [])
    if not criteria:
        return {}

    # Run spec-level checks once (they apply to all criteria)
    spec_evidence = await _collect_spec_evidence(spec, project_root)

    results: dict[int, CheckResult] = {}
    for i, criterion in enumerate(criteria):
        c_text = criterion.get("criterion", criterion) if isinstance(criterion, dict) else str(criterion)
        is_automated = criterion.get("automated", False) if isinstance(criterion, dict) else False

        # Start with spec-level evidence (code inspection, integration)
        evidence = list(spec_evidence)

        # Add test execution for automated criteria
        if is_automated and spec.get("test_requirements"):
            test_evidence = await run_test_execution(spec, project_root)
            evidence.append(test_evidence)

        results[i] = CheckResult(
            criterion_index=i,
            criterion_text=c_text,
            evidence=evidence,
        )

    return results


async def _collect_spec_evidence(
    spec: dict,
    project_root: str | None,
) -> list[BehavioralEvidence]:
    """Collect spec-level behavioral evidence (shared across all criteria)."""
    evidence: list[BehavioralEvidence] = []

    # Code inspection: always run if there are files to check
    has_files = spec.get("estimated_files") or spec.get("integration_points")
    if has_files:
        code_result = await run_code_inspection(spec, project_root)
        evidence.append(code_result)

    # Integration validation: only when integration_points exist
    if spec.get("integration_points"):
        integration_result = await run_integration_validation(spec, project_root)
        evidence.append(integration_result)

    return evidence
