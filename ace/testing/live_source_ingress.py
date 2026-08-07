"""Public conformance helper for governed LIVE source ingress."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ace.application.live_source_ingress import LiveSourceAdmission, LiveSourceIngressService
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from ace.intelligence.contracts.source_acquisition import LiveSourceIngressRequestV1Alpha1


@dataclass(frozen=True, slots=True)
class LiveSourceIngressConformanceResult:
    first: LiveSourceAdmission
    exact_replay: LiveSourceAdmission
    restarted_replay: LiveSourceAdmission


async def exercise_live_source_ingress_restart(
    *,
    first_service: LiveSourceIngressService,
    restarted_service: LiveSourceIngressService,
    request: LiveSourceIngressRequestV1Alpha1,
    pack: CompiledDomainPackV1,
) -> LiveSourceIngressConformanceResult:
    """Prove one commit and exact same-service/fresh-service replay publicly."""

    first = await first_service.admit(request=request, pack=pack)
    exact_replay = await first_service.admit(request=request, pack=pack)
    restarted_replay = await restarted_service.replay(request=request)
    if restarted_replay is None:
        raise AssertionError("fresh LIVE ingress service could not reopen the durable admission")
    if first.replayed or not exact_replay.replayed or not restarted_replay.replayed:
        raise AssertionError("LIVE ingress replay disposition was not explicit")
    expected = replace(first, replayed=False)
    if replace(exact_replay, replayed=False) != expected or replace(restarted_replay, replayed=False) != expected:
        raise AssertionError("LIVE ingress replay changed durable records or receipts")
    return LiveSourceIngressConformanceResult(
        first=first,
        exact_replay=exact_replay,
        restarted_replay=restarted_replay,
    )


__all__ = [
    "LiveSourceIngressConformanceResult",
    "exercise_live_source_ingress_restart",
]
