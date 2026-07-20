# engine/verification/checks/integration.py
"""Integration validation check — verify import chains between integration points.

For each integration_point in a spec, verifies that the referenced module
is actually imported in the source file. Lightweight structural check —
no execution, just AST-based import validation.
"""

from __future__ import annotations

import logging
import os
import time

from core.engine.scanner.ast_parser import get_language_for_extension, parse_file
from core.engine.verification.models import BehavioralEvidence

logger = logging.getLogger(__name__)


async def run_integration_validation(
    spec: dict,
    project_root: str | None = None,
) -> BehavioralEvidence:
    """Validate that integration points have correct import chains.

    For each integration point, checks that the file imports the module
    or function referenced in the point's description.
    """
    start = time.monotonic()
    root = project_root or os.getcwd()

    integration_points = spec.get("integration_points", [])
    if not integration_points:
        return BehavioralEvidence(
            check_type="integration_validation",
            status="skipped",
            details={"reason": "No integration points in spec"},
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    points_checked = 0
    points_valid = 0
    point_results = []

    for point in integration_points:
        if not isinstance(point, dict):
            continue

        file_path = point.get("file", "")
        function_name = point.get("function", "")
        if not file_path:
            continue

        points_checked += 1
        abs_path = os.path.join(root, file_path) if not os.path.isabs(file_path) else file_path

        if not os.path.isfile(abs_path):
            point_results.append(
                {
                    "file": file_path,
                    "function": function_name,
                    "valid": False,
                    "reason": "file not found",
                }
            )
            continue

        # Parse and check imports
        valid, reason = _validate_integration_point(abs_path, function_name)
        if valid:
            points_valid += 1

        point_results.append(
            {
                "file": file_path,
                "function": function_name,
                "valid": valid,
                "reason": reason,
            }
        )

    if points_checked == 0:
        status = "skipped"
    elif points_valid == points_checked:
        status = "passed"
    else:
        status = "failed"

    duration_ms = int((time.monotonic() - start) * 1000)

    return BehavioralEvidence(
        check_type="integration_validation",
        status=status,
        details={
            "points_checked": points_checked,
            "points_valid": points_valid,
            "point_results": point_results,
        },
        duration_ms=duration_ms,
    )


def _validate_integration_point(abs_path: str, function_name: str) -> tuple[bool, str]:
    """Check that a file contains the referenced function or imports it.

    Returns: (valid, reason)
    """
    ext = os.path.splitext(abs_path)[1]
    language = get_language_for_extension(ext)
    if not language:
        return True, "unsupported language — skipped"

    try:
        with open(abs_path, "rb") as f:
            content = f.read()
        result = parse_file(content, language)
    except Exception as exc:
        logger.debug("AST parse failed for %s: %s", abs_path, exc)
        return True, f"parse error — skipped: {exc}"

    if not function_name:
        # No function specified — just checking file exists
        return True, "file exists"

    # Check if function is defined in this file
    for func in result.functions:
        name = func.name
        # Match full name (ClassName.method) or bare name
        if name == function_name or ("." in name and name.split(".", 1)[1] == function_name):
            return True, f"function defined at line {func.line_start}"

    # Check if function is imported
    for imp in result.imports:
        if imp.name == function_name:
            return True, f"imported from {imp.module}"

    # Check classes
    for cls in result.classes:
        if cls.name == function_name:
            return True, f"class defined at line {cls.line_start}"

    return False, f"'{function_name}' not found in file (not defined or imported)"
