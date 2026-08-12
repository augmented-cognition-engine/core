"""Task-local internal selection state for the governed AC2 journey."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

from core.engine.core.agent_composition_runtime import (
    AuthenticatedRuntimeContextV1Alpha1,
    DomainActivationLineageV1Alpha1,
    ExactArtifactReferenceV1Alpha1,
)
from core.engine.orchestration.agent_composition_bridge import LegacyOrchestrationCompositionBridge


@dataclass(frozen=True, slots=True)
class GovernedCompositionTaskContext:
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    bridge: LegacyOrchestrationCompositionBridge
    trigger_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...] = ()
    activation_lineage: DomainActivationLineageV1Alpha1 | None = None


_CURRENT: ContextVar[GovernedCompositionTaskContext | None] = ContextVar(
    "governed_composition_task_context",
    default=None,
)


def current_governed_composition() -> GovernedCompositionTaskContext | None:
    return _CURRENT.get()


def bind_governed_composition(context: GovernedCompositionTaskContext) -> Token:
    return _CURRENT.set(context)


def reset_governed_composition(token: Token) -> None:
    _CURRENT.reset(token)


__all__ = [
    "GovernedCompositionTaskContext",
    "bind_governed_composition",
    "current_governed_composition",
    "reset_governed_composition",
]
