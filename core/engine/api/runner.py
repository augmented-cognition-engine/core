from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user
from core.engine.core.db import parse_one, parse_rows, pool

router = APIRouter(tags=["runner"])

# Module-level reference set by lifespan
_runner = None


def set_runner(runner):
    global _runner
    _runner = runner


def get_runner():
    if _runner is None:
        raise HTTPException(503, "Runner not initialized")
    return _runner


class EnqueueRequest(BaseModel):
    description: str
    title: str = ""
    priority: int = 100
    source: str = "user"
    initiative_id: str | None = None
    work_item_id: str | None = None
    dependencies: list[str] = []


@router.get("/runner/status")
async def runner_status(user=Depends(get_current_user)):
    runner = get_runner()
    return await runner.get_status()


@router.post("/runner/start")
async def runner_start(user=Depends(get_current_user)):
    runner = get_runner()
    if not runner._running:
        await runner.start()
    return {"status": "running"}


@router.post("/runner/stop")
async def runner_stop(user=Depends(get_current_user)):
    runner = get_runner()
    await runner.stop()
    return {"status": "stopped"}


@router.post("/runner/pause")
async def runner_pause(user=Depends(get_current_user)):
    product = user.get("product", "product:default")
    async with pool.connection() as db:
        await db.query(
            "UPDATE runner_config SET status = 'paused', mode = 'paused', updated_at = time::now() WHERE product = <record>$product",
            {"product": product},
        )
    return {"status": "paused"}


@router.post("/runner/resume")
async def runner_resume(user=Depends(get_current_user)):
    product = user.get("product", "product:default")
    async with pool.connection() as db:
        await db.query(
            "UPDATE runner_config SET status = 'running', mode = 'all', updated_at = time::now() WHERE product = <record>$product",
            {"product": product},
        )
    return {"status": "running"}


@router.put("/runner/config")
async def update_config(
    max_concurrent: int | None = None,
    mode: str | None = None,
    auto_approve: bool | None = None,
    user=Depends(get_current_user),
):
    product = user.get("product", "product:default")
    updates = []
    params = {"product": product}
    if max_concurrent is not None:
        updates.append("max_concurrent = $max")
        params["max"] = max(1, min(10, max_concurrent))
    if mode is not None:
        updates.append("mode = $mode")
        params["mode"] = mode
    if auto_approve is not None:
        updates.append("auto_approve = $auto")
        params["auto"] = auto_approve
    if updates:
        updates.append("updated_at = time::now()")
        async with pool.connection() as db:
            await db.query(
                f"UPDATE runner_config SET {', '.join(updates)} WHERE product = <record>$product",
                params,
            )
    return {"updated": True}


@router.get("/queue")
async def list_queue(user=Depends(get_current_user)):
    product = user.get("product", "product:default")
    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM task_queue WHERE product = <record>$product ORDER BY priority ASC, created_at ASC",
            {"product": product},
        )
        items = parse_rows(result)
    return {"items": items}


@router.post("/queue/enqueue")
async def enqueue(req: EnqueueRequest, user=Depends(get_current_user)):
    product = user.get("product", "product:default")
    async with pool.connection() as db:
        result = await db.query(
            """
            CREATE task_queue SET
                title = $title,
                description = $description,
                priority = $priority,
                source = $source,
                initiative_id = $init_id,
                work_item_id = $wi_id,
                dependencies = $deps,
                status = 'queued',
                created_at = time::now()
            """,
            {
                "product": product,
                "title": req.title or req.description[:80],
                "description": req.description,
                "priority": req.priority,
                "source": req.source,
                "init_id": req.initiative_id,
                "wi_id": req.work_item_id,
                "deps": req.dependencies,
            },
        )
        item = parse_one(result) or {}
    return item


@router.patch("/queue/{item_id}/priority")
async def update_priority(item_id: str, priority: int, user=Depends(get_current_user)):
    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET priority = $p",
            {"id": item_id, "p": priority},
        )
    return {"id": item_id, "priority": priority}


@router.delete("/queue/{item_id}")
async def remove_from_queue(item_id: str, user=Depends(get_current_user)):
    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET status = 'cancelled'",
            {"id": item_id},
        )
    return {"id": item_id, "status": "cancelled"}
