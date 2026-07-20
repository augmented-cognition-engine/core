# engine/mcp/schemas.py
"""Input/output schemas for ACE MCP tools."""

from pydantic import BaseModel, Field

# --- Tier 1: Pre-flight ---


class AceStartOutput(BaseModel):
    briefing_available: bool
    last_briefing_date: str | None = None
    active_initiatives: int = 0
    ideas_ready: int = 0
    pending_approvals: int = 0


class AceLoadInput(BaseModel):
    topic: str = Field(description="Domain topic or domain_path to load intelligence for")


class AceLoadOutput(BaseModel):
    domain_path: str
    insights: list[dict] = []
    corrections: list[dict] = []
    preferences: list[dict] = []
    framework_recommendation: str | None = None
    total_count: int = 0


class AceCaptureInput(BaseModel):
    observation_type: str = Field(description="Type: correction, decision, preference, pattern, learning, error")
    content: str = Field(description="The observation content")
    domain_path: str = Field(description="Domain path (e.g., design_systems.tokens)")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence 0-1")


class AceCaptureOutput(BaseModel):
    status: str
    id: str


# --- Tier 2: Task execution ---


class AceTaskInput(BaseModel):
    description: str = Field(description="Task description")
    skill_hint: str | None = Field(default=None, description="Force a specific skill slug")
    frameworks_hint: list[str] | None = Field(default=None, description="Suggest reasoning frameworks")


class AceTaskOutput(BaseModel):
    id: str
    discipline: str
    domain_path: str
    archetype: str
    mode: str
    perspective: str
    output: str
    intelligence_loaded: dict = {}
    status: str
    skill_used: str | None = None
    skill_slug: str | None = None
    jobs_completed: list[str] | None = None
    strategies_used: list[str] | None = None
    composition_pattern: str | None = None
    engagement: dict | None = None
    token_usage: dict | None = None


class AceStatusInput(BaseModel):
    filter: str | None = Field(default=None, description="Filter: active, blocked, waiting_approval")


class AceStatusOutput(BaseModel):
    initiatives: list[dict] = []
    ideas_ready: int = 0
    pending_approvals: int = 0


# --- Tier 3: Capture + escalation ---


class AceCaptureIdeaInput(BaseModel):
    raw_idea: str = Field(description="Raw idea text")
    context: str | None = Field(default=None, description="Additional context")


class AceSearchInput(BaseModel):
    query: str = Field(description="Search query")
    knowledge_type: str | None = Field(default=None, description="Filter: insight, correction, preference")


class AceSearchOutput(BaseModel):
    results: list[dict] = []
    count: int = 0


class AceBriefingInput(BaseModel):
    date: str | None = Field(default=None, description="Specific date (YYYY-MM-DD), defaults to latest")


class AceBriefingOutput(BaseModel):
    content: str | None = None
    period: str = ""
    created_at: str = ""
    metrics: dict = {}
    available: bool = False


# --- Graph tools ---


class AceImpactInput(BaseModel):
    file_path: str = Field(description="File path to analyze, e.g. 'engine/core/db.py'")
    graph_id: str = Field(default="default", description="Graph ID (default: 'default')")


class AceHistoryInput(BaseModel):
    file_path: str = Field(description="File path to look up decision history for")
    graph_id: str = Field(default="default", description="Graph ID (default: 'default')")


class AceRelatedInput(BaseModel):
    file_path: str = Field(description="File path to find connections for")
    graph_id: str = Field(default="default", description="Graph ID (default: 'default')")


class AceContextOutput(BaseModel):
    capabilities: list[dict] = []
    quality_summary: dict = {}
    recent_decisions: list[dict] = []
    active_work: dict = {}
    open_gaps: list[dict] = []
    recent_activity: list[dict] = []
    efficiency: dict = {}


class AcePRReviewInput(BaseModel):
    pr_url: str = Field(description="GitHub PR URL (e.g. https://github.com/owner/repo/pull/123)")
    disciplines: list[str] | None = Field(
        default=None, description="Override discipline selection (e.g. ['security', 'testing'])"
    )
    post_review: bool = Field(default=False, description="Post review comments back to GitHub")


class AcePRReviewOutput(BaseModel):
    pr_number: int = 0
    title: str = ""
    findings_count: int = 0
    findings: list[dict] = Field(default_factory=list)
    summary: str = ""
    discipline_scores: dict[str, float] = Field(default_factory=dict)
    pass_quality_gate: bool = True
    gate_failures: list[str] = Field(default_factory=list)
    impact: dict = Field(default_factory=dict)
