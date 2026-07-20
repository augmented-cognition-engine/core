"""SSE endpoint for LIVE layer real-time updates."""

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from core.engine.core.auth import get_current_user
from core.engine.live.stream import live_event_generator

router = APIRouter(tags=["live"])


@router.get("/stream/live")
async def live_stream(user=Depends(get_current_user)):
    """SSE stream of LIVE layer state changes."""
    product_id = user.get("product", "")
    return EventSourceResponse(live_event_generator(product_id), ping=15)
