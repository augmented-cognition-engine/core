# engine/api/reports.py
"""Reports API — generate and download consulting PDF reports."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateRequest(BaseModel):
    report_type: str = "audit"
    client_name: str = ""
    consultant_name: str = ""
    product_id: str = ""  # caller-supplied engagement; validated against tenant


def _safe_filename_segment(value: str) -> str:
    """Strip non-alphanumeric/hyphen chars to prevent Content-Disposition injection."""
    return re.sub(r"[^\w\-]", "", value.lower().replace(" ", "-")) or "report"


@router.post("/generate")
async def generate_report(
    body: GenerateRequest,
    user: dict = Depends(get_current_user),
):
    """Generate a consulting PDF report and return it as a file download."""
    user_product_id = user.get("product", "")
    if not user_product_id:
        raise HTTPException(status_code=400, detail="No product associated with account")
    if body.report_type not in ("audit", "snapshot"):
        raise HTTPException(status_code=400, detail="report_type must be 'audit' or 'snapshot'")

    # Resolve which product to use: caller-supplied (if in same tenant) or user's own.
    product_id = user_product_id
    if body.product_id and body.product_id != user_product_id:
        from core.engine.core.db import parse_rows as _pr

        try:
            async with pool.connection() as db:
                # Verify the supplied product belongs to the same tenant
                tenant_result = await db.query(
                    "SELECT tenant FROM product WHERE id = <record>$pid LIMIT 1",
                    {"pid": body.product_id},
                )
                user_tenant_result = await db.query(
                    "SELECT tenant FROM product WHERE id = <record>$pid LIMIT 1",
                    {"pid": user_product_id},
                )
            t_rows = _pr(tenant_result)
            u_rows = _pr(user_tenant_result)
            if t_rows and u_rows and t_rows[0].get("tenant") == u_rows[0].get("tenant"):
                product_id = body.product_id
        except Exception:
            pass  # fall back to user's product

    try:
        from core.engine.reports.generator import ReportGenerator

        gen = ReportGenerator(pool)
        pdf_bytes = await gen.generate(
            product_id=product_id,
            report_type=body.report_type,
            client_name=body.client_name,
            consultant_name=body.consultant_name,
        )
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Report generation failed")

    # Persist report metadata so list endpoint has records to return.
    try:
        async with pool.connection() as db:
            await db.query(
                """CREATE report SET
                   product = <record>$product,
                   type = $type,
                   client_name = $client_name,
                   consultant_name = $consultant_name,
                   status = 'complete',
                   created_at = time::now()""",
                {
                    "product": product_id,
                    "type": body.report_type,
                    "client_name": body.client_name,
                    "consultant_name": body.consultant_name,
                },
            )
    except Exception as exc:
        logger.warning("Failed to persist report record: %s", exc)
        # Non-fatal — PDF was generated, still return it.

    safe_name = _safe_filename_segment(body.client_name)
    filename = f"ace-{body.report_type}-{safe_name}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/")
async def list_reports(
    all_products: bool = False,
    product_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """List previously generated reports.

    - all_products=true  → tenant-wide (all engagements)
    - product_id=<id>    → specific engagement only (must belong to same tenant)
    - default            → user's own product from JWT
    """
    from core.engine.core.db import parse_rows as _parse_rows

    user_product_id = user.get("product", "")
    if not user_product_id:
        raise HTTPException(status_code=400, detail="No product associated with account")

    try:
        if all_products:
            async with pool.connection() as db:
                t_result = await db.query(
                    "SELECT tenant FROM product WHERE id = <record>$product LIMIT 1",
                    {"product": user_product_id},
                )
                t_rows = _parse_rows(t_result)
                if not t_rows or not t_rows[0].get("tenant"):
                    return {"reports": []}
                tenant = str(t_rows[0]["tenant"])

                result = await db.query(
                    """SELECT id, product AS product_id, type, client_name, consultant_name, status, created_at
                       FROM report
                       WHERE product INSIDE (SELECT VALUE id FROM product WHERE tenant = <record>$tenant)
                       ORDER BY created_at DESC
                       LIMIT 100""",
                    {"tenant": tenant},
                )
            return {"reports": _parse_rows(result)}

        # Resolve which product to filter by
        filter_product = product_id if product_id else user_product_id

        async with pool.connection() as db:
            result = await db.query(
                """SELECT id, product AS product_id, type, client_name, consultant_name, status, created_at
                   FROM report
                   WHERE product = <record>$product
                   ORDER BY created_at DESC
                   LIMIT 20""",
                {"product": filter_product},
            )
        return {"reports": parse_rows(result)}
    except Exception as exc:
        logger.error("Failed to list reports: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list reports")
