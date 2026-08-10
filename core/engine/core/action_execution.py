"""Supported host composition for governed action execution.

Applications explicitly register trusted action adapters by exact artifact identity.
Core resolves no entry points, imports no Domain Pack code, and owns persistence
through its immutable-record port.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Iterable, Protocol

from ace.core.action_execution import (
    GovernedActionAuthorizer,
    GovernedActionExecutionService,
)
from ace.core.reasoning import GovernedOperationBindingV1Alpha1
from ace.core.records import ImmutableRecordStore
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1


class ActionAdapterPort(Protocol):
    """Structural public port implemented by a trusted application or extension."""

    artifact_identity: CapabilityArtifactIdentityV1Alpha1

    async def prepare(self, intent: Any) -> Any: ...

    async def execute(self, plan: Any, authorization: Any) -> Any: ...


class ActionCompositionError(RuntimeError):
    """The host could not compose one exact governed action boundary."""


def _artifact_key(artifact: CapabilityArtifactIdentityV1Alpha1) -> tuple[str, str, str, str, str]:
    return (
        artifact.capability,
        artifact.contract,
        artifact.implementation_id,
        artifact.implementation_version,
        artifact.artifact_digest,
    )


class BoundedActionAdapterRegistry:
    """Constructor-only registry keyed by the complete immutable artifact identity.

    Registration is an explicit host decision. There is no package discovery,
    dynamic import, prefix match, or version fallback.
    """

    def __init__(self, adapters: Iterable[ActionAdapterPort] = ()) -> None:
        self._adapters: dict[tuple[str, str, str, str, str], ActionAdapterPort] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ActionAdapterPort) -> None:
        try:
            identity = CapabilityArtifactIdentityV1Alpha1.model_validate(
                adapter.artifact_identity.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ActionCompositionError("action adapter lacks an exact artifact identity") from exc
        if identity.capability != "bounded_action_execution" or identity.contract != "ace.core.action-adapter/v1alpha1":
            raise ActionCompositionError("action adapter does not implement the bounded Core contract")
        key = _artifact_key(identity)
        if key in self._adapters:
            raise ActionCompositionError("action adapter artifact identity is already registered")
        self._adapters[key] = adapter

    def resolve(self, artifact: CapabilityArtifactIdentityV1Alpha1) -> ActionAdapterPort | None:
        try:
            exact = CapabilityArtifactIdentityV1Alpha1.model_validate(artifact.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ActionCompositionError("requested action adapter identity is invalid") from exc
        return self._adapters.get(_artifact_key(exact))


def build_governed_action_execution_service(
    *,
    store: ImmutableRecordStore,
    authorizer: GovernedActionAuthorizer,
    operation_binding: GovernedOperationBindingV1Alpha1,
    adapters: BoundedActionAdapterRegistry,
    clock: Callable[[], datetime],
) -> GovernedActionExecutionService:
    """Compose one service only when the exact governed adapter is installed."""

    try:
        binding = GovernedOperationBindingV1Alpha1.model_validate(operation_binding.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ActionCompositionError("governed action operation binding is invalid") from exc
    adapter = adapters.resolve(binding.artifact)
    if adapter is None:
        raise ActionCompositionError("exact governed action adapter is not registered")
    return GovernedActionExecutionService(
        store=store,
        authorizer=authorizer,
        operation_binding=binding,
        adapter=adapter,  # type: ignore[arg-type]
        clock=clock,
    )


def build_surreal_governed_action_execution_service(
    *,
    db: Any,
    authorizer: GovernedActionAuthorizer,
    operation_binding: GovernedOperationBindingV1Alpha1,
    adapters: BoundedActionAdapterRegistry,
    clock: Callable[[], datetime],
) -> GovernedActionExecutionService:
    """Compose the supported durable host path over SurrealDB."""

    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    return build_governed_action_execution_service(
        store=SurrealImmutableRecordStore(db),
        authorizer=authorizer,
        operation_binding=operation_binding,
        adapters=adapters,
        clock=clock,
    )


__all__ = [
    "ActionAdapterPort",
    "ActionCompositionError",
    "BoundedActionAdapterRegistry",
    "build_governed_action_execution_service",
    "build_surreal_governed_action_execution_service",
]
