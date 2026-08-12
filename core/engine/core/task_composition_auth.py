"""Task-path-only post-JWT authentication evidence adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends

from core.engine.core.agent_composition_runtime import ImmutableRecordStore, persist_task_authentication_receipt
from core.engine.core.auth import get_current_user
from core.engine.orchestration.agent_composition_bridge import LegacyOrchestrationCompositionBridge
from core.engine.orchestration.agent_composition_context import GovernedCompositionTaskContext

_PRIVATE_ENVELOPE_KEY = "__ace_governed_composition_task_context__"


@dataclass(frozen=True, slots=True)
class TaskCompositionAuthenticationHost:
    records: ImmutableRecordStore
    bridge: LegacyOrchestrationCompositionBridge
    verification_policy_ref: str


_HOST: TaskCompositionAuthenticationHost | None = None


def configure_task_composition_authentication(host: TaskCompositionAuthenticationHost | None) -> None:
    """Explicit host composition; ``None`` preserves the legacy task journey."""

    global _HOST
    _HOST = host


async def get_task_current_user(user: dict = Depends(get_current_user)) -> dict:
    """Return the same claims plus a private, non-serializable governed envelope."""

    host = _HOST
    if host is None:
        return user
    receipt = await persist_task_authentication_receipt(
        claims=user,
        verified_at=datetime.now(UTC),
        store=host.records,
        verification_policy_ref=host.verification_policy_ref,
    )
    enriched = dict(user)
    enriched[_PRIVATE_ENVELOPE_KEY] = GovernedCompositionTaskContext(
        authenticated_context=receipt.runtime_context(),
        bridge=host.bridge,
    )
    return enriched


def governed_composition_from_user(user: dict) -> GovernedCompositionTaskContext | None:
    value = user.get(_PRIVATE_ENVELOPE_KEY)
    return value if isinstance(value, GovernedCompositionTaskContext) else None


__all__ = [
    "TaskCompositionAuthenticationHost",
    "configure_task_composition_authentication",
    "get_task_current_user",
    "governed_composition_from_user",
]
