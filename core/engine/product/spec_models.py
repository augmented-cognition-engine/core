"""Pydantic models for agent specs and feedback in the agentic PM layer."""

from typing import Optional

from pydantic import BaseModel, field_validator

SPEC_STATUSES = {"draft", "approved", "executing", "verifying", "completed", "failed"}
FEEDBACK_TYPES = {"blocker", "discovery", "trade_off", "scope_question", "completion", "progress"}
SPEC_SOURCES = {"gap", "idea", "human", "pm_initiative"}


class AcceptanceCriterion(BaseModel):
    """A single verifiable condition for spec completion."""

    criterion: str
    verification: str = ""  # how to verify this criterion
    automated: bool = False  # can be verified programmatically?


class AgentSpecCreate(BaseModel):
    """Create a new agent-executable spec."""

    objective: str
    source: str  # gap, idea, human, pm_initiative
    source_id: Optional[str] = None  # reference to gap/idea/question that triggered this
    capability_slug: Optional[str] = None
    acceptance_criteria: list[AcceptanceCriterion]
    constraints: Optional[list[str]] = None
    integration_points: Optional[list[dict]] = None  # [{file, function, description}]
    estimated_files: Optional[list[str]] = None
    test_requirements: Optional[list[str]] = None
    best_practices: Optional[list[str]] = None
    context: Optional[dict] = None

    @field_validator("source")
    @classmethod
    def validate_source(cls, v):
        if v not in SPEC_SOURCES:
            raise ValueError(f"source must be one of {SPEC_SOURCES}")
        return v

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_criteria_not_empty(cls, v):
        if not v:
            raise ValueError("acceptance_criteria must have at least one criterion")
        return v


class AgentSpecUpdate(BaseModel):
    """Update an existing spec."""

    status: Optional[str] = None
    objective: Optional[str] = None
    acceptance_criteria: Optional[list[AcceptanceCriterion]] = None
    constraints: Optional[list[str]] = None
    context: Optional[dict] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in SPEC_STATUSES:
            raise ValueError(f"status must be one of {SPEC_STATUSES}")
        return v


class AgentFeedbackCreate(BaseModel):
    """Structured feedback from an agent to the PM."""

    spec_id: str
    feedback_type: str
    content: str
    work_unit: Optional[str] = None
    context: Optional[dict] = None  # type-specific context

    @field_validator("feedback_type")
    @classmethod
    def validate_type(cls, v):
        if v not in FEEDBACK_TYPES:
            raise ValueError(f"feedback_type must be one of {FEEDBACK_TYPES}")
        return v


class VerificationResult(BaseModel):
    """Result of acceptance verification."""

    spec_id: str
    overall: str  # fully_met, partially_met, not_met
    criteria_results: list[dict]  # [{criterion, status, evidence}]
    quality_delta: Optional[dict] = None  # {dimension: {before, after}}
    follow_up_needed: bool = False

    @field_validator("overall")
    @classmethod
    def validate_overall(cls, v):
        if v not in {"fully_met", "partially_met", "not_met"}:
            raise ValueError("overall must be fully_met, partially_met, or not_met")
        return v
