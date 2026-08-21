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
    IntelligenceBuildFirstBriefRequestV1Alpha2,
    IntelligenceBuildInitialCorpusFirstBriefRequestV1Alpha1,
)
from ace.application.intelligence_ledger import resource_reference
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
from ace.core.contracts import canonical_hash
from core.engine.core.local_source_connect import LocalSourceConnectRecordRepository

PERSONAL_PROFILE_ID = "intelligence_onboarding_profile:personal"
PERSONAL_ORIENTATION_POLICY_ID = "personal_initial_orientation"

# The Pack declares one content-revision detector per mapped entity type
# (PI13 §10). Which detector watches which type is Personal product knowledge,
# so it lives here beside the profile it serves rather than in generic Core.
_REVISION_DETECTOR_BY_ENTITY_TYPE: dict[str, str] = {
    "note": "personal_note_revised",
    "document": "personal_document_revised",
}

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
        self._reingested_without_change = False
        self._build_id = ""
        self._build_request_digest = ""

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
        self._build_id = build.build_id
        self._build_request_digest = build.request_digest
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

        if host_services.prepared_derivations is None:
            raise PersonalIntelligenceBuildExecutorError(
                "the Personal build executor requires a prepared-derivation port to tell a revision from a first read"
            )

        admission = await host_services.recorded_sources.admit(tuple(materials))
        corpus_as_of, corpus_available_at = self._admitted_corpus_cut(build, admission)

        # Re-ingest: every admitted entity is compared against its own prior
        # state. Core resolves the `prior_snapshot` baseline each detector rule
        # declares, so the executor never selects one itself.
        revisions = await self._derive_revisions(
            build,
            host_services,
            admission=admission,
            evaluated_at=corpus_available_at,
        )
        if revisions:
            for outcome in revisions:
                await self._route_brief_revision(host_services, outcome=outcome, requested_at=corpus_available_at)
            return await self._project(host_services, as_of=corpus_as_of, available_at=corpus_available_at)
        if self._reingested_without_change:
            # An unchanged re-read is a truthful non-event: no orientation is
            # re-derived and no revision is invented.
            return await self._project(host_services, as_of=corpus_as_of, available_at=corpus_available_at)

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

        return await self._project(host_services, as_of=corpus_as_of, available_at=corpus_available_at)

    async def _project(
        self,
        host_services: IntelligenceBuildHostServices,
        *,
        as_of: datetime,
        available_at: datetime,
    ) -> IntelligenceResourcePageV1Alpha1:
        return await host_services.resources.query(
            resource_kinds=_QUERIED_RESOURCE_KINDS,
            subject_refs=(),
            as_of=as_of,
            available_at=available_at,
            evaluated_at=available_at,
            page_size=200,
        )

    async def _derive_revisions(
        self,
        build: AuthorizedIntelligenceBuild,
        host_services: IntelligenceBuildHostServices,
        *,
        admission: RecordedSourceAdmission,
        evaluated_at: datetime,
    ) -> tuple[object, ...]:
        """Compare each admitted entity against its own prior admitted state.

        ``derive_against_prior_snapshot`` returns ``None`` when the entity has no
        earlier snapshot, which is how a first admission is recognised without
        guessing. A returned outcome that is not material means the source was
        re-read unchanged.
        """

        self._reingested_without_change = False
        material: list[object] = []
        for entity in admission.entity_snapshots:
            entity_type = str(entity.entity_type_ref).split(":")[-1]
            detector_id = _REVISION_DETECTOR_BY_ENTITY_TYPE.get(entity_type)
            if detector_id is None:
                raise PersonalIntelligenceBuildExecutorError(
                    f"no Personal revision detector is declared for entity type {entity.entity_type_ref!r}"
                )
            outcome = await host_services.prepared_derivations.derive_against_prior_snapshot(
                derivation_key=self._derivation_key(build, entity_ref=str(entity.entity_ref)),
                detector_id=detector_id,
                current_snapshot=resource_reference(entity),
                evaluated_at=evaluated_at,
            )
            if outcome is None:
                continue
            if getattr(outcome, "material_shift", False):
                material.append(outcome)
            else:
                self._reingested_without_change = True
        return tuple(material)

    async def _route_brief_revision(
        self,
        host_services: IntelligenceBuildHostServices,
        *,
        outcome: object,
        requested_at: datetime,
    ) -> None:
        """Append one routed Brief revision for one exact material Shift."""

        admission = getattr(outcome, "admission", None)
        receipt = getattr(admission, "attention_receipt", None)
        derivation_key = getattr(getattr(outcome, "request", None), "derivation_key", None)
        if receipt is None or derivation_key is None:
            raise PersonalIntelligenceBuildExecutorError(
                "a material revision must carry its exact derivation key and attention receipt"
            )
        try:
            request = IntelligenceBuildFirstBriefRequestV1Alpha2(
                build_id=self._build_id,
                build_request_digest=self._build_request_digest,
                derivation_key=str(derivation_key),
                attention_receipt_id=str(receipt.receipt_id),
                attention_receipt_digest=str(receipt.receipt_digest),
                requested_at=requested_at,
            )
        except (TypeError, ValueError) as exc:
            raise PersonalIntelligenceBuildExecutorError(
                "derived revision does not bind an exact routed first-Brief request"
            ) from exc
        await host_services.first_brief.create_first_brief(request)

    @staticmethod
    def _derivation_key(build: AuthorizedIntelligenceBuild, *, entity_ref: str) -> str:
        """Deterministic per build and entity, so a retry replays one derivation."""

        digest = canonical_hash([build.build_id, build.request_digest, entity_ref])
        return f"prepared_derivation:{digest[:32]}"

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
