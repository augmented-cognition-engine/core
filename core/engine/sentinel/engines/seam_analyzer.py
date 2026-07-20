"""Seam Analyzer — detect API contract mismatches between backend and frontend."""

from __future__ import annotations

import glob
import logging
from dataclasses import asdict

from core.engine.core.db import pool
from core.engine.core.exceptions import ValidationError
from core.engine.seam.backend_extractor import extract_backend_contracts
from core.engine.seam.frontend_extractor import extract_frontend_expectations
from core.engine.seam.matcher import match_and_compare
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)


def _validate_seam_analyzer_inputs(product_id: str, budget: int = 100) -> None:
    """Validate seam analyzer inputs before querying the database.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast with a clear error rather than running LLM
    calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for seam-analyzer: {product_id!r}")
    if not (0 <= budget <= 500):
        raise ValidationError(f"budget must be in [0, 500], got {budget}")


@register_engine(
    name="seam_analyzer",
    cron="0 4 * * *",
    description="Detect API contract mismatches between backend endpoints and frontend consumers.",
)
async def run_seam_analyzer(product_id: str, budget: int = 0) -> dict:
    _validate_seam_analyzer_inputs(product_id, budget)
    # 1. Find backend API files
    backend_files = glob.glob("engine/api/*.py")
    contracts = []
    for f in backend_files:
        try:
            contracts.extend(extract_backend_contracts(f))
        except Exception as exc:
            logger.warning("Backend extraction failed for %s: %s", f, exc)

    # 2. Find frontend files
    tsx_files = glob.glob("portal/src/**/*.tsx", recursive=True)
    ts_files = glob.glob("portal/src/**/*.ts", recursive=True)
    frontend_files = tsx_files + ts_files

    # 3. Type source files
    type_files = glob.glob("portal/src/types/*.ts")

    # 4. Extract frontend expectations
    expectations = []
    for f in frontend_files:
        try:
            expectations.extend(extract_frontend_expectations(f, type_files))
        except Exception as exc:
            logger.warning("Frontend extraction failed for %s: %s", f, exc)

    # 5. Match and compare
    gaps = match_and_compare(contracts, expectations)

    # 6. Store in SurrealDB
    errors = 0
    warnings = 0
    infos = 0

    async with pool.connection() as db:
        await db.query(
            "DELETE seam_gap WHERE product = <record>$product",
            {"product": product_id},
        )

        for gap in gaps:
            gap_dict = asdict(gap)
            await db.query(
                """CREATE seam_gap SET
                    route = <string>$route,
                    severity = <string>$severity,
                    gap_type = <string>$gap_type,
                    backend_file = <string>$backend_file,
                    frontend_file = <string>$frontend_file,
                    detail = <string>$detail,
                    detected_at = time::now()""",
                {"product": product_id, **gap_dict},
            )

            if gap.severity == "error":
                errors += 1
            elif gap.severity == "warning":
                warnings += 1
            else:
                infos += 1

    return {
        "contracts_found": len(contracts),
        "expectations_found": len(expectations),
        "gaps_total": len(gaps),
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
    }
