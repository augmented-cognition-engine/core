"""Route matcher + field comparator for seam analysis.

Pairs SeamContracts (backend) with SeamExpectations (frontend) by
normalized route, then compares field names to surface mismatches.
"""

from __future__ import annotations

import re
from collections import defaultdict

from core.engine.seam.types import SeamContract, SeamExpectation, SeamGap


def normalize_route(route: str) -> str:
    """Normalize a route for comparison.

    - Strip query strings (everything after ?)
    - Strip leading and trailing /
    - Collapse path params: {anything} -> {}
    - Return lowercase
    """
    # Strip query string
    route = route.split("?", 1)[0]

    # Strip leading/trailing slashes
    route = route.strip("/")

    # Collapse path params
    route = re.sub(r"\{[^}]*\}", "{}", route)

    return route.lower()


def match_and_compare(
    contracts: list[SeamContract],
    expectations: list[SeamExpectation],
) -> list[SeamGap]:
    """Match contracts to expectations by route and compare fields.

    Returns a list of SeamGap describing mismatches:
    - unmatched_route (info): frontend expects a route with no backend contract
    - missing_field (error): frontend expects a field the backend doesn't provide
    - extra_field (warning): backend provides a field the frontend doesn't use
    """
    # Build lookup: (normalized_route, method) -> list of contracts
    lookup: dict[tuple[str, str], list[SeamContract]] = defaultdict(list)
    for contract in contracts:
        key = (normalize_route(contract.route), contract.method.upper())
        lookup[key].append(contract)

    gaps: list[SeamGap] = []

    for expectation in expectations:
        key = (normalize_route(expectation.route), expectation.method.upper())
        matching_contracts = lookup.get(key)

        if not matching_contracts:
            gaps.append(
                SeamGap(
                    route=expectation.route,
                    severity="info",
                    gap_type="unmatched_route",
                    frontend_file=expectation.consumer_file,
                    detail=f"No backend contract for {expectation.method.upper()} {expectation.route}",
                )
            )
            continue

        # Use first matching contract for field comparison
        contract = matching_contracts[0]

        # Skip comparison when backend has empty response_fields
        # (can't compare — avoid false positives)
        if not contract.response_fields:
            continue

        backend_names = {f.name for f in contract.response_fields}
        frontend_names = {f.name for f in expectation.expected_fields}

        # Fields expected by frontend but missing from backend → error
        for name in sorted(frontend_names - backend_names):
            gaps.append(
                SeamGap(
                    route=expectation.route,
                    severity="error",
                    gap_type="missing_field",
                    backend_file=contract.source_file,
                    frontend_file=expectation.consumer_file,
                    detail=f"Frontend expects '{name}' but backend does not provide it",
                )
            )

        # Fields in backend but not used by frontend → warning
        for name in sorted(backend_names - frontend_names):
            gaps.append(
                SeamGap(
                    route=expectation.route,
                    severity="warning",
                    gap_type="extra_field",
                    backend_file=contract.source_file,
                    frontend_file=expectation.consumer_file,
                    detail=f"Backend provides '{name}' but frontend does not use it",
                )
            )

    return gaps
