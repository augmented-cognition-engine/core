"""Public, domain-neutral ACE Intelligence contracts and pure derivation logic.

Importing this package performs no discovery, I/O, compilation, activation,
or host composition. Runtime engines and application services are separate
bounded contexts layered on these contracts. The pure interpretation modules
exported here (routing, synthesis, epistemic, detection, source mapping) are
deterministic functions over contract values only.
"""

from ace.intelligence.conformance import conformance_receipt_json, run_domain_pack_conformance
from ace.intelligence.contracts import *  # noqa: F403
from ace.intelligence.contracts import __all__ as _CONTRACTS_ALL
from ace.intelligence.derivation import (
    COLLAPSING_RELATIONS,
    DERIVATION_FAMILY_POLICY,
    DerivationFamilyClosure,
    DerivationFamilyError,
    derive_observation_families,
    independent_family_roots,
)
from ace.intelligence.detection import (
    CategoricalTransitionDetectionError,
    NumericDeltaDetectionError,
    detect_categorical_shift,
    detect_live_categorical_shift,
    detect_live_numeric_shift,
    detect_numeric_shift,
    route_categorical_shift_as_signal,
    route_live_categorical_shift_as_signal,
    route_live_shift_as_signal,
    route_shift_as_signal,
)
from ace.intelligence.epistemic import (
    BriefClaimEpistemicStatusBindingV1Alpha1,
    BriefClaimEpistemicStatusBindingV1Alpha2,
    BriefSynthesisDraftV1Alpha2,
    EpistemicStatusDeclarationV1,
    EpistemicStatusDeclarationV1Alpha2,
    EpistemicStatusValidationError,
    ResolvedEpistemicStatusPolicy,
    derive_claim_epistemic_statuses,
    derive_claim_epistemic_statuses_with_families,
)
from ace.intelligence.impact import ResolvedImpactEvidence, evaluate_measured_impact
from ace.intelligence.measured_composition import compare_measured_composition
from ace.intelligence.routing import (
    EligibleSignalRoute,
    SignalRoutingError,
    eligible_live_signal_routes,
    eligible_signal_routes,
)
from ace.intelligence.source_mapping import (
    LiveSourceMappingError,
    LiveSourceMappingResult,
    PreparedSourceMappingError,
    PreparedSourceMappingResult,
    interpret_live_source_mapping,
    interpret_prepared_source_mapping,
)
from ace.intelligence.supersession import (
    IMPACT_RELATIONS,
    SUPERSEDING_RELATION,
    SUPERSESSION_IMPACT_POLICY,
    ImpactedResource,
    SupersessionImpact,
    SupersessionImpactError,
    project_claim_impact,
    project_supersession_impact,
)
from ace.intelligence.synthesis import (
    BriefDraftValidationError,
    CanonicalBriefAssembly,
    ResolvedBriefSynthesisPolicy,
    assemble_canonical_brief,
    canonical_executive_summary,
    render_canonical_brief_body,
    validate_brief_synthesis_draft,
)

__all__ = [
    "BriefClaimEpistemicStatusBindingV1Alpha1",
    "BriefClaimEpistemicStatusBindingV1Alpha2",
    "BriefSynthesisDraftV1Alpha2",
    "EpistemicStatusDeclarationV1",
    "EpistemicStatusDeclarationV1Alpha2",
    "ResolvedEpistemicStatusPolicy",
    "ResolvedBriefSynthesisPolicy",
    *_CONTRACTS_ALL,
    "BriefDraftValidationError",
    "COLLAPSING_RELATIONS",
    "DERIVATION_FAMILY_POLICY",
    "DerivationFamilyClosure",
    "DerivationFamilyError",
    "IMPACT_RELATIONS",
    "ResolvedImpactEvidence",
    "ImpactedResource",
    "SUPERSEDING_RELATION",
    "SUPERSESSION_IMPACT_POLICY",
    "SupersessionImpact",
    "SupersessionImpactError",
    "derive_observation_families",
    "independent_family_roots",
    "project_claim_impact",
    "project_supersession_impact",
    "CanonicalBriefAssembly",
    "CategoricalTransitionDetectionError",
    "EligibleSignalRoute",
    "EpistemicStatusValidationError",
    "LiveSourceMappingError",
    "LiveSourceMappingResult",
    "NumericDeltaDetectionError",
    "PreparedSourceMappingError",
    "PreparedSourceMappingResult",
    "SignalRoutingError",
    "assemble_canonical_brief",
    "canonical_executive_summary",
    "derive_claim_epistemic_statuses",
    "derive_claim_epistemic_statuses_with_families",
    "detect_categorical_shift",
    "detect_live_categorical_shift",
    "detect_live_numeric_shift",
    "detect_numeric_shift",
    "eligible_live_signal_routes",
    "eligible_signal_routes",
    "evaluate_measured_impact",
    "compare_measured_composition",
    "conformance_receipt_json",
    "interpret_live_source_mapping",
    "interpret_prepared_source_mapping",
    "render_canonical_brief_body",
    "route_categorical_shift_as_signal",
    "route_live_categorical_shift_as_signal",
    "route_live_shift_as_signal",
    "route_shift_as_signal",
    "run_domain_pack_conformance",
    "validate_brief_synthesis_draft",
]
