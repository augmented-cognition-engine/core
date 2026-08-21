"""First-party Personal Intelligence build executor (WS3).

This module closes the missing production seam between an authorized
Personal Intelligence build and the reviewed, already-recorded Connect
captures it must admit: it reopens each exact stored capture by its reviewed
selection reference (never rereading the source or mutating captured bytes),
binds the capture's declared subject through the build's recorded-source
port, admits the resulting recorded material, and returns the resource page
Core projects for the exact authorized build.

It lives in the host layer beside the other first-party product applications
(``core/engine/code_intelligence``, ``core/engine/personal_intelligence``);
``ace/core`` and ``ace/intelligence`` gain no Personal noun (packet
Decision 1). Every intelligence-bounded-context name below is reached
through its public ``ace.application`` surface.
"""

from __future__ import annotations

from datetime import datetime

from ace.application.intelligence_build_execution import (
    AuthorizedIntelligenceBuild,
    IntelligenceBuildHostServices,
    IntelligenceBuildStartV1Alpha2,
)
from ace.application.intelligence_build_first_brief import (
    IntelligenceBuildInitialCorpusFirstBriefRequestV1Alpha1,
)
from ace.application.intelligence_resource_plane import (
    IntelligenceResourceKind,
    IntelligenceResourcePageV1Alpha1,
)
from ace.application.recorded_source_admission import (
    IntelligenceResourceMode,
    RecordedSourceAdmission,
    RecordedSourceMaterialV1Alpha1,
    resource_available_at,
)
from core.engine.core.local_source_connect import LocalSourceConnectRecordRepository

PERSONAL_PROFILE_ID = "intelligence_onboarding_profile:personal"
PERSONAL_ORIENTATION_POLICY_ID = "personal_initial_orientation"

_QUERIED_RESOURCE_KINDS: tuple[IntelligenceResourceKind, ...] = (
    IntelligenceResourceKind.SOURCE_HEALTH,
    IntelligenceResourceKind.ENTITY,
    IntelligenceResourceKind.OBSERVATION,
    IntelligenceResourceKind.BRIEF,
)


class PersonalIntelligenceBuildExecutorError(RuntimeError):
    """The Personal build executor's exact material failed closed."""


class PersonalIntelligenceBuildExecutor:
    """Executes the shipped Personal onboarding profile's recorded-source build.

    Zero-arg constructible: the build executor registry instantiates
    entry-point classes with no arguments, mirroring the planner registry's
    zero-arg contract.
    """

    profile_id = PERSONAL_PROFILE_ID

    def __init__(self) -> None:
        self.profile_id = PERSONAL_PROFILE_ID

    async def start(
        self,
        build: AuthorizedIntelligenceBuild,
        host_services: IntelligenceBuildHostServices,
    ) -> IntelligenceResourcePageV1Alpha1:
        if not isinstance(build.request, IntelligenceBuildStartV1Alpha2) or build.request.profile_id != self.profile_id:
            raise PersonalIntelligenceBuildExecutorError(
                "the Personal build executor executes only the Personal onboarding profile's v1alpha2 request"
            )
        if host_services.recorded_sources is None:
            raise PersonalIntelligenceBuildExecutorError(
                "the Personal build executor requires a recorded-source admission port"
            )
        if host_services.first_brief is None:
            raise PersonalIntelligenceBuildExecutorError(
                "the Personal build executor requires an initial-corpus first-Brief port"
            )
        selection_refs = build.request.recorded_source_selection_refs
        if not selection_refs:
            raise PersonalIntelligenceBuildExecutorError(
                "the Personal build executor requires at least one reviewed recorded source selection"
            )

        repository = LocalSourceConnectRecordRepository(host_services.records)
        materials: list[RecordedSourceMaterialV1Alpha1] = []
        for ref in selection_refs:
            capture = await repository.load_capture(build.product_id, ref, actor_ref=build.actor_ref)
            selection = capture.selection
            if selection.reference() != ref:
                raise PersonalIntelligenceBuildExecutorError(
                    "reopened Connect capture does not bind the exact reviewed selection reference"
                )
            subject = host_services.recorded_sources.bind_subject(
                subject_binding_id=selection.subject_binding_id,
                entity_type_id=selection.entity_type_id,
                entity_ref=selection.entity_ref,
            )
            materials.append(
                RecordedSourceMaterialV1Alpha1(
                    source_group_id=selection.source_group_id,
                    mapping_id=selection.mapping_id,
                    subject_binding=subject,
                    source_definition_ref=selection.source_definition_ref,
                    source_type_ref=selection.source_type_ref,
                    source_uri=selection.source_uri,
                    captured_payload_json=capture.structured_payload_json,
                    captured_payload_digest=selection.captured_payload_digest,
                    source_published_at=selection.source_published_at,
                    event_effective_at=selection.event_effective_at,
                    observed_at=selection.observed_at,
                    locator=selection.locator,
                    acquisition_mode=capture.acquisition_mode,
                )
            )

        admission = await host_services.recorded_sources.admit(tuple(materials))
        corpus_as_of, corpus_available_at = self._admitted_corpus_cut(build, admission)

        try:
            first_brief_request = IntelligenceBuildInitialCorpusFirstBriefRequestV1Alpha1(
                build_id=build.build_id,
                build_request_digest=build.request_digest,
                orientation_policy_id=PERSONAL_ORIENTATION_POLICY_ID,
                corpus_as_of=corpus_as_of,
                corpus_available_at=corpus_available_at,
                requested_at=corpus_available_at,
            )
        except (TypeError, ValueError) as exc:
            raise PersonalIntelligenceBuildExecutorError(
                "admitted first-corpus cut does not bind an exact initial-corpus first-Brief request"
            ) from exc
        await host_services.first_brief.create_initial_corpus_first_brief(first_brief_request)

        return await host_services.resources.query(
            resource_kinds=_QUERIED_RESOURCE_KINDS,
            subject_refs=(),
            as_of=corpus_as_of,
            available_at=corpus_available_at,
            evaluated_at=corpus_available_at,
            page_size=200,
        )

    @staticmethod
    def _admitted_corpus_cut(
        build: AuthorizedIntelligenceBuild,
        admission: RecordedSourceAdmission,
    ) -> tuple[datetime, datetime]:
        """Derive the exact J5 corpus cut from the retained admission alone.

        The cut never comes from the wall clock, a reread, or a synthetic
        Shift/Signal: ``corpus_as_of`` is the one shared ``as_of`` across every
        admitted Observation and Entity Snapshot, and the availability/request
        instant is the admission transaction's ``committed_at``, which must not
        itself run past the authorized build's own evaluated_at -- otherwise
        ``create_initial_corpus_first_brief``, which re-resolves current build
        authority at ``requested_at``, would be asked to move that authority
        into the future.
        """

        if not isinstance(admission, RecordedSourceAdmission):
            raise PersonalIntelligenceBuildExecutorError(
                "recorded-source admission did not return exact admission material"
            )
        try:
            receipt = admission.transaction_receipt
            if receipt.product_id != build.product_id:
                raise PersonalIntelligenceBuildExecutorError(
                    "recorded-source admission transaction crossed the authorized build product"
                )
            committed_at = receipt.committed_at
            if not admission.observations or not admission.entity_snapshots:
                raise PersonalIntelligenceBuildExecutorError(
                    "recorded-source admission must return admitted Observation and Entity Snapshot material"
                )
            corpus = tuple(admission.observations) + tuple(admission.entity_snapshots)
            for resource in corpus:
                if resource.product_id != build.product_id or resource.mode is not IntelligenceResourceMode.PREPARED:
                    raise PersonalIntelligenceBuildExecutorError(
                        "admitted first-corpus material crossed the authorized product or PREPARED mode"
                    )
                if resource_available_at(resource) > committed_at:
                    raise PersonalIntelligenceBuildExecutorError(
                        "admitted first-corpus material cannot become available after its admission commit"
                    )
            as_of_values = {resource.as_of for resource in corpus}
            if len(as_of_values) != 1:
                raise PersonalIntelligenceBuildExecutorError(
                    "admitted first-corpus material must share one exact as_of"
                )
            if committed_at > build.authority_use.evaluated_at:
                raise PersonalIntelligenceBuildExecutorError(
                    "admission commit cannot follow the authorized build's current authority evaluated_at"
                )
        except PersonalIntelligenceBuildExecutorError:
            raise
        except (AttributeError, TypeError) as exc:
            raise PersonalIntelligenceBuildExecutorError(
                "recorded-source admission failed exact fail-closed validation"
            ) from exc
        return next(iter(as_of_values)), committed_at


__all__ = [
    "PERSONAL_ORIENTATION_POLICY_ID",
    "PERSONAL_PROFILE_ID",
    "PersonalIntelligenceBuildExecutor",
    "PersonalIntelligenceBuildExecutorError",
]
