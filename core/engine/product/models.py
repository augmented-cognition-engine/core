from typing import Optional

from pydantic import BaseModel, field_validator

CAPABILITY_STATUSES = {"planned", "building", "built", "partial", "deprecated", "missing"}
QUALITY_DIMENSIONS = {
    "security",
    "testing",
    "ux",
    "performance",
    "devops",
    "data",
    "accessibility",
    "documentation",
    "architecture",
    "api_design",
    "data_modeling",
    "business_logic",
    "integration",
    "error_handling",
    "observability",
    "configuration",
    "deployment",
    "versioning",
    "code_conventions",
    "dependency_management",
}
QUESTION_CATEGORIES = {"inward", "downward", "outward", "forward", "temporal"}
QUESTION_PRIORITIES = {"critical", "high", "medium", "low"}
DEP_TYPES = {"requires", "enhances", "replaces", "conflicts"}

PRODUCT_TYPES = {
    "ai_native",
    "trading_system",
    "content_site",
    "enterprise_ds",
    "internal_tool",
    "mobile_consumer_app",
    "ecommerce",
    "dev_tool",
    "mobile_game",
}

PRODUCT_SCALES = ["atomic", "component", "application", "platform", "enterprise"]

PHASES = ["discovery", "poc", "alpha", "beta", "ga", "mature"]


class CapabilityCreate(BaseModel):
    name: str
    slug: str
    description: str
    status: str = "built"
    intent: Optional[dict] = None
    reality: Optional[dict] = None
    parent_id: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[list[str]] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in CAPABILITY_STATUSES:
            raise ValueError(f"status must be one of {CAPABILITY_STATUSES}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if v is not None and v not in {"critical", "important", "nice_to_have"}:
            raise ValueError("priority must be critical, important, or nice_to_have")
        return v


class CapabilityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    intent: Optional[dict] = None
    reality: Optional[dict] = None
    priority: Optional[str] = None
    tags: Optional[list[str]] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in CAPABILITY_STATUSES:
            raise ValueError(f"status must be one of {CAPABILITY_STATUSES}")
        return v


class CapabilityProposal(BaseModel):
    name: str
    slug: str
    description: str
    file_glob: str
    file_ids: list[str]
    intent: Optional[str] = None
    confidence: float = 0.5

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v


class VisionCreate(BaseModel):
    name: str
    description: str = ""
    active: bool = True


class ThemeCreate(BaseModel):
    name: str
    description: str = ""
    status: str = "active"


class QualityAssessment(BaseModel):
    dimension: str
    score: float
    gaps: Optional[list[str]] = None
    evidence: Optional[list[str]] = None
    assessed_by: str = "human"

    @field_validator("dimension")
    @classmethod
    def validate_dimension(cls, v):
        if v not in QUALITY_DIMENSIONS:
            raise ValueError(f"dimension must be one of {QUALITY_DIMENSIONS}")
        return v

    @field_validator("score")
    @classmethod
    def validate_score(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")
        return v


class QuestionCreate(BaseModel):
    question: str
    category: str
    source: str
    capability_id: Optional[str] = None
    priority: str = "medium"
    status: str = "open"

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v not in QUESTION_CATEGORIES:
            raise ValueError(f"category must be one of {QUESTION_CATEGORIES}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if v not in QUESTION_PRIORITIES:
            raise ValueError(f"priority must be one of {QUESTION_PRIORITIES}")
        return v
