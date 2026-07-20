"""Pure routing: a classification -> the canvas response type. The single place
intent routing lives; thresholds are explicit and tunable."""

from __future__ import annotations

from enum import Enum
from typing import Any

NON_ANALYTICAL_TASK_TYPES = {"communicate", "note"}
DECISION_TASK_TYPES = {"evaluate", "review"}
CODE_DISCIPLINES = {"technology", "scale"}
CODE_TASK_TYPES = {"implement", "code", "build", "refactor", "debug"}


class ResponseType(str, Enum):
    STICKY = "sticky"
    ANGLE = "angle"
    TRADE_OFF_MATRIX = "trade_off_matrix"
    DESIGN_OPTIONS = "design_options"
    CODE_ARCHITECTURE = "code_architecture"
    REASONING = "reasoning"


def route(classification: dict[str, Any]) -> ResponseType:
    complexity = classification.get("complexity", "moderate")
    task_type = classification.get("task_type", "")
    discipline = classification.get("discipline", "")

    if complexity == "ambiguous":
        return ResponseType.ANGLE
    if complexity == "simple" and task_type in NON_ANALYTICAL_TASK_TYPES:
        return ResponseType.STICKY
    if task_type in DECISION_TASK_TYPES:
        return ResponseType.TRADE_OFF_MATRIX
    if task_type == "design" or discipline == "ux":
        return ResponseType.DESIGN_OPTIONS
    if discipline in CODE_DISCIPLINES and task_type in CODE_TASK_TYPES:
        return ResponseType.CODE_ARCHITECTURE
    return ResponseType.REASONING
