"""Index which functions are referenced from test files.

For each graph_function in non-test files, determine if any function in a
test file (path matching tests/** or *_test.py or test_*.py) calls it.

Stored as graph_function.test_refs: array<record<graph_function>>.
The regression guard reads this for precise advisories instead of
heuristic naming checks.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

_TEST_PATH_MARKERS = ("tests/", "/test_", "_test.py", "/tests/")


def is_test_path(path: str) -> bool:
    return any(marker in path for marker in _TEST_PATH_MARKERS)


async def reindex_test_refs(product_id: str) -> dict:
    """Walk all graph_function records, populate test_refs.

    Strategy:
    1. Pull all test functions (functions in test files)
    2. Build reverse index: source function name → [test function ids that call it]
    3. Bulk UPDATE graph_function SET test_refs = [ids]

    Returns: {functions_indexed, test_functions, untested_count}
    """
    try:
        async with pool.connection() as db:
            funcs = parse_rows(
                await db.query("SELECT id, name, file_path, calls FROM graph_function WHERE graph_id = 'default'")
            )
    except Exception as exc:
        logger.debug("reindex_test_refs: DB query failed: %s", exc)
        return {"functions_indexed": 0, "test_functions": 0, "untested_count": 0}

    test_funcs = [f for f in funcs if is_test_path(f.get("file_path", ""))]
    src_funcs = [f for f in funcs if not is_test_path(f.get("file_path", ""))]

    # Build reverse index: source_function_name → [test function IDs]
    refs: dict[str, list[str]] = defaultdict(list)
    for t in test_funcs:
        for callee in t.get("calls") or []:
            callee_key = str(callee).split(":")[-1] if ":" in str(callee) else str(callee)
            refs[callee_key].append(str(t["id"]))

    updated = 0
    try:
        async with pool.connection() as db:
            for fn in src_funcs:
                test_ids = refs.get(fn["name"], [])
                await db.query(
                    "UPDATE $fid SET test_refs = $refs",
                    {"fid": fn["id"], "refs": test_ids},
                )
                updated += 1
    except Exception as exc:
        logger.debug("reindex_test_refs: UPDATE failed at %d: %s", updated, exc)

    return {
        "functions_indexed": updated,
        "test_functions": len(test_funcs),
        "untested_count": sum(1 for f in src_funcs if not refs.get(f["name"])),
    }


async def has_test_reference(function_name: str, file_path: str) -> bool:
    """Fast lookup used by the regression guard hook.

    Returns True if any function in graph_function.test_refs covers this function.
    Returns False on DB miss or DB unavailable (regression guard stays advisory).
    """
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT test_refs FROM graph_function
                WHERE name = $name AND file_path = $file LIMIT 1""",
                    {"name": function_name, "file": file_path},
                )
            )
        if not rows:
            return False
        return bool(rows[0].get("test_refs"))
    except Exception:
        return False
