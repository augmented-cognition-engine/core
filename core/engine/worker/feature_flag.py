from __future__ import annotations

from core.engine.core.db import parse_rows


async def is_worker_canvas_bridge_enabled(pool, product_id: str) -> bool:
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT enabled FROM product_feature_flag
               WHERE product = <record>$pid
                 AND flag = 'worker_canvas_bridge_enabled' LIMIT 1""",
                {"pid": product_id},
            )
        )
    if not rows:
        return False
    return bool(rows[0].get("enabled", False))


async def set_worker_canvas_bridge_enabled(pool, product_id: str, enabled: bool) -> None:
    async with pool.connection() as db:
        await db.query(
            """UPSERT product_feature_flag CONTENT {
                product: <record>$pid,
                flag: 'worker_canvas_bridge_enabled',
                enabled: <bool>$v,
                set_at: time::now()
            } WHERE product = <record>$pid AND flag = 'worker_canvas_bridge_enabled'""",
            {"pid": product_id, "v": enabled},
        )
