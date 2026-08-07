"""Host composition adapters wiring governed LIVE cognition into core.engine.

This module is the only sanctioned host edge for the LIVE application
services: connectors register through the bounded registry below and every
composed service persists exclusively through Core's immutable-record port,
so no connector or pack gains dynamic loading or a persistence bypass.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Iterable, Protocol

from ace.application.domain_activation import DomainActivationAdmissionService
from ace.application.live_intelligence_bridge import (
    GovernedActionAuthorizer,
    LiveBriefSynthesisService,
    LiveIntelligenceBridgeService,
)
from ace.application.live_source_ingress import LiveSourceIngressService
from ace.core.reasoning import (
    GovernedOperationBindingV1Alpha1,
    GovernedReasoningService,
    ReasoningExecutionBindingV1Alpha1,
)
from ace.core.records import ImmutableRecordStore
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1, RuntimeUseResolver
from ace.core.source import SourceDefinitionResolver


class SourceAdapterPort(Protocol):
    """Structural mirror of the public source-adapter contract.

    Declared locally so this host edge depends only on Core public ports;
    conformance with ace.intelligence.contracts.source_acquisition is
    enforced structurally and by exact-identity revalidation at register.
    """

    artifact_identity: CapabilityArtifactIdentityV1Alpha1

    async def capture(self, request: Any) -> Any: ...


class LiveCompositionError(RuntimeError):
    """Host LIVE composition failed closed."""


def _artifact_key(artifact: CapabilityArtifactIdentityV1Alpha1) -> tuple[str, str, str, str, str]:
    return (
        artifact.capability,
        artifact.contract,
        artifact.implementation_id,
        artifact.implementation_version,
        artifact.artifact_digest,
    )


class BoundedSourceAdapterRegistry:
    """Constructor-registered source adapters keyed by exact artifact identity.

    No entry points, no import hooks: the host names every installed adapter
    explicitly, and resolution is an exact-identity lookup that returns None
    for anything not registered.
    """

    def __init__(self, adapters: Iterable[SourceAdapterPort] = ()) -> None:
        self._adapters: dict[tuple[str, str, str, str, str], SourceAdapterPort] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: SourceAdapterPort) -> None:
        try:
            identity = CapabilityArtifactIdentityV1Alpha1.model_validate(
                adapter.artifact_identity.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveCompositionError("source adapter lacks an exact artifact identity") from exc
        key = _artifact_key(identity)
        if key in self._adapters:
            raise LiveCompositionError("source adapter artifact identity is already registered")
        self._adapters[key] = adapter

    def resolve_source_adapter(
        self,
        *,
        artifact: CapabilityArtifactIdentityV1Alpha1,
    ) -> SourceAdapterPort | None:
        return self._adapters.get(_artifact_key(artifact))


def build_live_source_ingress_service(
    *,
    activation_service: DomainActivationAdmissionService,
    source_definitions: SourceDefinitionResolver,
    runtime_use: RuntimeUseResolver,
    adapters: BoundedSourceAdapterRegistry,
    store: ImmutableRecordStore,
    clock: Callable[[], datetime] | None = None,
    max_payload_chars: int = 1_000_000,
) -> LiveSourceIngressService:
    kwargs: dict[str, Any] = {}
    if clock is not None:
        kwargs["clock"] = clock
    return LiveSourceIngressService(
        activation_service=activation_service,
        source_definitions=source_definitions,
        runtime_use=runtime_use,
        adapters=adapters,
        store=store,
        max_payload_chars=max_payload_chars,
        **kwargs,
    )


def build_live_intelligence_bridge_service(
    *,
    activation_service: DomainActivationAdmissionService,
    pack: Any,
    store: ImmutableRecordStore,
    authorizer: GovernedActionAuthorizer,
    operation_binding: GovernedOperationBindingV1Alpha1,
) -> LiveIntelligenceBridgeService:
    return LiveIntelligenceBridgeService(
        activation_service=activation_service,
        pack=pack,
        store=store,
        authorizer=authorizer,
        operation_binding=operation_binding,
    )


def build_live_brief_synthesis_service(
    *,
    activation_service: DomainActivationAdmissionService,
    pack: Any,
    store: ImmutableRecordStore,
    reasoning: GovernedReasoningService,
    execution_binding: ReasoningExecutionBindingV1Alpha1,
    append_binding: GovernedOperationBindingV1Alpha1,
) -> LiveBriefSynthesisService:
    return LiveBriefSynthesisService(
        activation_service=activation_service,
        pack=pack,
        store=store,
        reasoning=reasoning,
        execution_binding=execution_binding,
        append_binding=append_binding,
    )


def build_surreal_live_record_store(db: Any) -> ImmutableRecordStore:
    """Compose the host's governed immutable-record store for LIVE spaces."""

    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    return SurrealImmutableRecordStore(db)


def utc_clock() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "BoundedSourceAdapterRegistry",
    "SourceAdapterPort",
    "LiveCompositionError",
    "build_live_brief_synthesis_service",
    "build_live_intelligence_bridge_service",
    "build_live_source_ingress_service",
    "build_surreal_live_record_store",
    "utc_clock",
]
