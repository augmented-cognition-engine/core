from pydantic import BaseModel


class QueueItem(BaseModel):
    id: str = ""
    org: str = ""
    title: str = ""
    description: str = ""
    domain_path: str = ""
    priority: int = 100
    status: str = "queued"
    source: str = "user"
    work_item_id: str | None = None
    initiative_id: str | None = None
    slot_number: int | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class RunnerConfig(BaseModel):
    max_concurrent: int = 3
    mode: str = "all"  # all, user_only, paused
    auto_approve: bool = True
    status: str = "running"


class RunnerStatus(BaseModel):
    running: bool = False
    config: RunnerConfig = RunnerConfig()
    active_count: int = 0
    queued_count: int = 0
    completed_today: int = 0
    daily_cost: float = 0.0
    active_items: list[QueueItem] = []
