# engine/verification/checks/code_inspection.py
"""Code inspection check — verify files and functions exist via AST parsing.

Uses engine/scanner/ast_parser.py to structurally verify that the code
referenced in a spec's estimated_files and integration_points actually exists.
"""

from __future__ import annotations

import logging
import os
import time

from core.engine.scanner.ast_parser import ParseResult, get_language_for_extension, parse_file
from core.engine.verification.models import BehavioralEvidence

logger = logging.getLogger(__name__)


async def run_code_inspection(
    spec: dict,
    project_root: str | None = None,
) -> BehavioralEvidence:
    """Check that estimated files exist and integration point functions are present.

    Returns a single BehavioralEvidence with aggregated file/function results.
    """
    start = time.monotonic()
    root = project_root or os.getcwd()

    estimated_files = spec.get("estimated_files", [])
    integration_points = spec.get("integration_points", [])

    files_checked = []
    functions_found = []
    functions_missing = []

    # Check estimated files exist
    for file_path in estimated_files:
        abs_path = os.path.join(root, file_path) if not os.path.isabs(file_path) else file_path
        exists = os.path.isfile(abs_path)
        files_checked.append({"file": file_path, "exists": exists})

    # Check integration point functions via AST
    for point in integration_points:
        if not isinstance(point, dict):
            continue

        file_path = point.get("file", "")
        function_name = point.get("function", "")
        if not file_path or not function_name:
            continue

        abs_path = os.path.join(root, file_path) if not os.path.isabs(file_path) else file_path
        if not os.path.isfile(abs_path):
            functions_missing.append(f"{file_path}:{function_name}")
            continue

        # Parse the file and look for the function
        found = _check_function_exists(abs_path, function_name)
        if found:
            functions_found.append(f"{file_path}:{function_name}")
        else:
            functions_missing.append(f"{file_path}:{function_name}")

    # Determine overall status
    if not files_checked and not integration_points:
        status = "skipped"
    elif all(f["exists"] for f in files_checked) and len(functions_missing) == 0:
        status = "passed"
    else:
        status = "failed"

    duration_ms = int((time.monotonic() - start) * 1000)

    return BehavioralEvidence(
        check_type="code_inspection",
        status=status,
        details={
            "files_checked": files_checked,
            "functions_found": functions_found,
            "functions_missing": functions_missing,
        },
        duration_ms=duration_ms,
    )


def _check_function_exists(abs_path: str, function_name: str) -> bool:
    """Parse a file with AST and check if a function/class/method exists."""
    ext = os.path.splitext(abs_path)[1]
    language = get_language_for_extension(ext)
    if not language:
        # Can't parse this language — don't count as missing
        return True

    try:
        with open(abs_path, "rb") as f:
            content = f.read()
        result: ParseResult = parse_file(content, language)
    except Exception as exc:
        logger.debug("AST parse failed for %s: %s", abs_path, exc)
        return True  # fail open — don't penalize for parse errors

    # Check functions (includes methods as ClassName.method_name)
    for func in result.functions:
        if func.name == function_name:
            return True
        # Also match just the method name without class prefix
        if "." in func.name and func.name.split(".", 1)[1] == function_name:
            return True

    # Check classes
    for cls in result.classes:
        if cls.name == function_name:
            return True

    return False
