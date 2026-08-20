"""First-party Personal Intelligence build planner (issue #252, 1.2.1).

The 1.2.0 acceptance run proved the ``ace.intelligence_build_planners``
entry-point group was empty in every public artifact, so ``builds/prepare``
failed closed with 503 and the Personal journey could not start. This module
is the missing first-party implementation: it plans — and can only plan — the
Personal Intelligence build for the shipped onboarding profile, proposing an
activation the owner must separately review, bind, and approve.

It lives in the host layer beside the other first-party product applications
(``core/engine/code_intelligence``); ``ace/core`` and ``ace/intelligence``
gain no Personal noun (packet Decision 1). The exact compiled pack identity is
resolved fail-closed from the co-installed pack tree, which has the same shape
for an installed wheel and a development checkout.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

# Host-layer boundary: core/engine never imports ace.intelligence directly.
# Every intelligence-bounded-context name below is reached through its public
# ace.application surface, mirroring the planner registry host adapter.
from ace.application.installed_pack_artifacts import compile_pack_document_with_report
from ace.application.intelligence_build_planning import (
    INTELLIGENCE_BUILD_PLANNER_V1ALPHA3_CONTRACT,
    INTELLIGENCE_BUILD_PLANNING_CAPABILITY,
    CompiledDomainPackV1,
    CompiledOverlayV1,
    CompiledPackRefV1,
    IntelligenceBuildActivationProposalV1Alpha1,
    IntelligenceBuildPlanRequestV1Alpha2,
    IntelligenceBuildPlanV1Alpha3,
    IntelligenceOnboardingProfileV1Alpha1,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from core.engine.version import VERSION

PERSONAL_PROFILE_ID = "intelligence_onboarding_profile:personal"
PERSONAL_PACK_ID = "personal_intelligence"
PERSONAL_ACTIVATION_KEY = "personal_intelligence"


class PersonalIntelligencePlannerError(RuntimeError):
    """The Personal planner's exact material failed closed."""


def _pack_root() -> Path:
    """The co-installed pack tree.

    The pack distribution installs its inert tree at
    ``<site-packages>/domain_packs/personal_intelligence`` — the same shape a
    source checkout has relative to this module — so one resolution path
    serves the installed wheel and the development checkout alike.
    """

    candidate = Path(__file__).resolve().parents[3] / "domain_packs" / PERSONAL_PACK_ID
    if not (candidate / "manifest.json").is_file():
        raise PersonalIntelligencePlannerError(
            "the Personal Intelligence pack is not installed beside ace-core; "
            "install the ace-personal-intelligence-pack distribution"
        )
    return candidate


def _resolve_personal_pack_reference() -> CompiledPackRefV1:
    pack_root = _pack_root()
    manifest_document = (pack_root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_document)
    resources = {item["path"]: (pack_root / item["path"]).read_bytes() for item in manifest["resources"]}
    pack = compile_pack_document_with_report(manifest_document, resources).pack
    return CompiledPackRefV1(
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        compiled_pack_id=pack.compiled_pack_id,
        pack_digest=pack.pack_digest,
    )


class PersonalIntelligenceBuildPlanner:
    """Authority-neutral planner for the shipped Personal onboarding profile."""

    def __init__(self, pack_reference: CompiledPackRefV1) -> None:
        self.profile_id = PERSONAL_PROFILE_ID
        self.pack_reference = pack_reference
        self.artifact_identity = CapabilityArtifactIdentityV1Alpha1(
            capability=INTELLIGENCE_BUILD_PLANNING_CAPABILITY,
            contract=INTELLIGENCE_BUILD_PLANNER_V1ALPHA3_CONTRACT,
            implementation_id="personal_intelligence_build_planner",
            implementation_version=VERSION,
            artifact_digest=f"sha256:{sha256(Path(__file__).read_bytes()).hexdigest()}",
        )

    async def prepare(
        self,
        request: IntelligenceBuildPlanRequestV1Alpha2,
        *,
        profile: IntelligenceOnboardingProfileV1Alpha1,
        pack: CompiledDomainPackV1,
    ) -> IntelligenceBuildPlanV1Alpha3:
        if request.profile_id != PERSONAL_PROFILE_ID or profile.profile_id != PERSONAL_PROFILE_ID:
            raise ValueError("the Personal planner plans only the Personal onboarding profile")
        if profile.profile_digest is not None and request.profile_digest != profile.profile_digest:
            raise ValueError("the plan request does not bind the exact onboarding profile material")
        if pack.metadata.pack_id != self.pack_reference.pack_id or pack.pack_digest != self.pack_reference.pack_digest:
            raise ValueError("the supplied pack is not the exact compiled Personal Intelligence pack")
        declared_groups = {item.source_group_id for item in profile.source_groups}
        undeclared = set(request.source_group_ids) - declared_groups
        if undeclared:
            raise ValueError(f"the plan request selects undeclared source groups: {sorted(undeclared)}")

        proposal = IntelligenceBuildActivationProposalV1Alpha1(
            product_id=request.product_id,
            activation_key=PERSONAL_ACTIVATION_KEY,
            pack=self.pack_reference,
            overlay=CompiledOverlayV1(
                overlay_id="personal_defaults",
                version="1.0.0",
                pack_id=self.pack_reference.pack_id,
                pack_version=self.pack_reference.pack_version,
                pack_digest=self.pack_reference.pack_digest,
            ),
            capability_requirement_ids=tuple(item.requirement_id for item in pack.capability_requirements),
            authority_request_ids=tuple(item.request_id for item in pack.authority_requests),
        )
        # Planning proposes; it never connects. Source selections are recorded
        # later, after the owner's consent-before-read authorization (J3), so
        # a fresh plan carries no recorded selections (profile guardrail:
        # proposed_sources_are_not_connected).
        return IntelligenceBuildPlanV1Alpha3(
            request=request,
            planner_artifact=self.artifact_identity,
            pack_reference=self.pack_reference,
            activation_proposal=proposal,
        )


def load_personal_intelligence_build_planner() -> PersonalIntelligenceBuildPlanner:
    """Entry-point target for ``ace.intelligence_build_planners``; fails closed."""

    return PersonalIntelligenceBuildPlanner(_resolve_personal_pack_reference())


__all__ = [
    "PERSONAL_ACTIVATION_KEY",
    "PERSONAL_PACK_ID",
    "PERSONAL_PROFILE_ID",
    "PersonalIntelligenceBuildPlanner",
    "PersonalIntelligencePlannerError",
    "load_personal_intelligence_build_planner",
]
