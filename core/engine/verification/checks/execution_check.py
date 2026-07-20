# engine/verification/checks/execution_check.py
"""Test execution check — run relevant pytest tests and capture results.

Runs tests in a subprocess with timeout to isolate from ACE's event loop.
Parses exit codes and stdout to produce structured evidence.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from core.engine.verification.models import BehavioralEvidence

logger = logging.getLogger(__name__)

# pytest exit codes
_EXIT_OK = 0  # all tests passed
_EXIT_TESTS_FAILED = 1  # some tests failed
_EXIT_INTERRUPTED = 2  # test run interrupted
_EXIT_INTERNAL_ERROR = 3  # internal pytest error
_EXIT_USAGE_ERROR = 4  # pytest usage error
_EXIT_NO_TESTS = 5  # no tests collected

_MAX_OUTPUT = 2000  # truncate test output for LLM prompt
_DEFAULT_TIMEOUT = 60  # seconds


async def run_test_execution(
    spec: dict,
    project_root: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> BehavioralEvidence:
    """Run pytest for test paths derived from the spec.

    Test path resolution:
    1. If test_requirements contain file paths (test_*.py), use directly
    2. Otherwise, infer test files from estimated_files
    """
    start = time.monotonic()
    root = project_root or os.getcwd()

    test_paths = _resolve_test_paths(spec, root)
    if not test_paths:
        return BehavioralEvidence(
            check_type="test_execution",
            status="skipped",
            details={"reason": "No test paths resolved from spec"},
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    # Run pytest in subprocess
    cmd = [
        "python",
        "-m",
        "pytest",
        "-x",  # stop on first failure
        "-q",  # quiet output
        "--tb=short",  # short tracebacks
        "-m",
        "not e2e",  # skip e2e tests
        *test_paths,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=root,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return BehavioralEvidence(
            check_type="test_execution",
            status="error",
            details={"reason": f"Test execution timed out after {timeout}s", "test_paths": test_paths},
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as exc:
        return BehavioralEvidence(
            check_type="test_execution",
            status="error",
            details={"reason": str(exc), "test_paths": test_paths},
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    output = stdout.decode(errors="replace")[:_MAX_OUTPUT]
    error_output = stderr.decode(errors="replace")[:500]
    exit_code = proc.returncode

    # Parse results from exit code
    status, tests_passed, tests_failed = _parse_results(exit_code, output)

    duration_ms = int((time.monotonic() - start) * 1000)

    return BehavioralEvidence(
        check_type="test_execution",
        status=status,
        details={
            "exit_code": exit_code,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "test_paths": test_paths,
            "output": output,
            "error_output": error_output if error_output else None,
        },
        duration_ms=duration_ms,
    )


def _resolve_test_paths(spec: dict, root: str) -> list[str]:
    """Resolve test file paths from spec metadata."""
    paths = []

    # First: check test_requirements for explicit file paths
    for req in spec.get("test_requirements", []):
        if isinstance(req, str) and ("test_" in req or "_test." in req) and req.endswith(".py"):
            abs_path = os.path.join(root, req)
            if os.path.isfile(abs_path):
                paths.append(req)

    if paths:
        return paths

    # Second: infer test files from estimated_files
    for file_path in spec.get("estimated_files", []):
        if not isinstance(file_path, str):
            continue
        basename = os.path.basename(file_path)
        if basename.startswith("test_"):
            # Already a test file
            abs_path = os.path.join(root, file_path)
            if os.path.isfile(abs_path):
                paths.append(file_path)
        else:
            # Try to find corresponding test file
            test_name = f"test_{basename}"
            # Look in tests/ directory
            test_path = os.path.join("tests", test_name)
            abs_path = os.path.join(root, test_path)
            if os.path.isfile(abs_path):
                paths.append(test_path)

    return paths


def _parse_results(exit_code: int, output: str) -> tuple[str, int, int]:
    """Parse pytest exit code and output into status and counts.

    Returns: (status, tests_passed, tests_failed)
    """
    if exit_code == _EXIT_OK:
        passed = _extract_count(output, "passed")
        return "passed", passed, 0

    if exit_code == _EXIT_TESTS_FAILED:
        passed = _extract_count(output, "passed")
        failed = _extract_count(output, "failed")
        return "failed", passed, failed

    if exit_code == _EXIT_NO_TESTS:
        return "skipped", 0, 0

    # Errors and interruptions
    return "error", 0, 0


def _extract_count(output: str, keyword: str) -> int:
    """Extract a count from pytest summary line like '3 passed, 1 failed'."""
    import re

    match = re.search(rf"(\d+)\s+{keyword}", output)
    return int(match.group(1)) if match else 0
