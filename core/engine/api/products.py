# engine/api/products.py
"""Products management API — list, create, and link repos to products."""

from __future__ import annotations

import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

router = APIRouter()
logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Convert a name to a lowercase underscore slug."""
    slug = re.sub(r"[^a-z0-9_]", "_", name.lower().strip())
    return re.sub(r"_+", "_", slug).strip("_")


@router.get("/products")
async def list_products(user=Depends(get_current_user)):
    """List all products for this tenant with health summary."""
    product_id = user.get("product", "")
    async with pool.connection() as db:
        t_result = await db.query(
            "SELECT tenant FROM product WHERE id = <record>$product LIMIT 1",
            {"product": product_id},
        )
        t_rows = parse_rows(t_result)
        tenant = str(t_rows[0]["tenant"]) if t_rows and t_rows[0].get("tenant") else "tenant:default"

        result = await db.query(
            "SELECT id, name, created_at FROM product WHERE tenant = <record>$tenant AND id != product:platform ORDER BY name",
            {"tenant": tenant},
        )
        products = parse_rows(result)

        # Enrich each product with health summary
        enriched = []
        for p in products:
            pid = str(p["id"])
            try:
                gate_r = await db.query(
                    "SELECT count() AS n FROM gate_evaluation WHERE product = <record>$product AND status = 'pending' GROUP ALL",
                    {"product": pid},
                )
                open_gates = int((parse_rows(gate_r) or [{}])[0].get("n", 0) or 0)

                init_r = await db.query(
                    "SELECT count() AS n FROM initiative WHERE product = <record>$product AND status = 'active' GROUP ALL",
                    {"product": pid},
                )
                active_inits = int((parse_rows(init_r) or [{}])[0].get("n", 0) or 0)

                at_risk_r = await db.query(
                    "SELECT count() AS n FROM initiative WHERE product = <record>$product AND status IN ['paused', 'blocked'] GROUP ALL",
                    {"product": pid},
                )
                at_risk = int((parse_rows(at_risk_r) or [{}])[0].get("n", 0) or 0)

                last_r = await db.query(
                    "SELECT created_at FROM task WHERE product = <record>$product ORDER BY created_at DESC LIMIT 1",
                    {"product": pid},
                )
                last_rows = parse_rows(last_r)
                last_activity = str(last_rows[0]["created_at"]) if last_rows else None

                health = "red" if at_risk > 0 else ("amber" if open_gates > 0 else "green")

                enriched.append(
                    {
                        **p,
                        "health": health,
                        "active_initiatives": active_inits,
                        "open_gates": open_gates,
                        "last_activity_at": last_activity,
                    }
                )
            except Exception as exc:
                logger.warning("Health enrichment failed for %s: %s", pid, exc)
                enriched.append(
                    {**p, "health": "green", "active_initiatives": 0, "open_gates": 0, "last_activity_at": None}
                )

    return {"products": enriched}


class CreateProductRequest(BaseModel):
    name: str
    repo_path: str | None = None


@router.post("/products", status_code=201)
async def create_product(body: CreateProductRequest, user=Depends(get_current_user)):
    """Create a product. Optionally links a repo path as the first project."""
    product_id = user.get("product", "")
    slug = _slugify(body.name)
    if not slug:
        raise HTTPException(status_code=422, detail="Name produces an empty slug")

    new_product_id = f"product:{slug}"

    async with pool.connection() as db:
        existing = await db.query(
            "SELECT id FROM product WHERE id = type::record('product', <string>$slug) LIMIT 1",
            {"slug": slug},
        )
        if parse_rows(existing):
            raise HTTPException(status_code=409, detail=f"Product '{slug}' already exists")

        t_result = await db.query(
            "SELECT tenant FROM product WHERE id = <record>$product LIMIT 1",
            {"product": product_id},
        )
        t_rows = parse_rows(t_result)
        tenant_param = str(t_rows[0]["tenant"]) if t_rows and t_rows[0].get("tenant") else "tenant:default"

        await db.query(
            """
            UPSERT type::record('product', <string>$slug) SET
                name       = $name,
                tenant     = <record>$tenant,
                settings   = {},
                created_at = time::now()
            """,
            {"slug": slug, "name": body.name, "tenant": tenant_param},
        )

        if body.repo_path:
            repo_basename = os.path.basename(body.repo_path.rstrip("/\\"))
            proj_slug = _slugify(repo_basename) or slug
            proj_id_slug = f"{slug}_{proj_slug}"
            # decision:8o4c6s8xxrxkov8xzbn1 — v061 dropped `org` from project.
            # Prior UPSERT had `org = <record>$product` and raised every call.
            # Same removal applies to /products/{slug}/link below.
            await db.query(
                """
                UPSERT type::record('project', <string>$proj_id) SET
                    product    = <record>$product,
                    name       = $repo_name,
                    slug       = <string>$proj_slug,
                    repo_path  = $repo_path,
                    created_at = time::now(),
                    updated_at = time::now()
                """,
                {
                    "proj_id": proj_id_slug,
                    "product": new_product_id,
                    "repo_name": repo_basename,
                    "proj_slug": proj_slug,
                    "repo_path": body.repo_path,
                },
            )

        result = await db.query(
            "SELECT id, name, created_at FROM product WHERE id = type::record('product', <string>$slug) LIMIT 1",
            {"slug": slug},
        )
        product = parse_one(result)

    return product or {"id": new_product_id, "name": body.name}


class LinkRequest(BaseModel):
    repo_path: str


@router.post("/products/{product_slug}/link", status_code=201)
async def link_repo(product_slug: str, body: LinkRequest, user=Depends(get_current_user)):
    """Create a project record linking a repo path to an existing product."""
    product_id = f"product:{product_slug}"

    async with pool.connection() as db:
        existing = await db.query(
            "SELECT id FROM product WHERE id = type::record('product', <string>$slug) LIMIT 1",
            {"slug": product_slug},
        )
        if not parse_rows(existing):
            raise HTTPException(status_code=404, detail=f"Product '{product_slug}' not found")

        repo_basename = os.path.basename(body.repo_path.rstrip("/\\"))
        proj_slug = _slugify(repo_basename) or product_slug
        proj_id_slug = f"{product_slug}_{proj_slug}"

        await db.query(
            """
            UPSERT type::record('project', <string>$proj_id) SET
                product    = <record>$product,
                name       = $repo_name,
                slug       = <string>$proj_slug,
                repo_path  = $repo_path,
                created_at = time::now(),
                updated_at = time::now()
            """,
            {
                "proj_id": proj_id_slug,
                "product": product_id,
                "repo_name": repo_basename,
                "proj_slug": proj_slug,
                "repo_path": body.repo_path,
            },
        )

    return {"product": product_id, "project": f"project:{proj_id_slug}", "repo_path": body.repo_path}
