"""Packaged conformance seams for external ACE bounded-context packages."""

from ace.testing.domain_pack import conformance_receipt_json, run_domain_pack_conformance
from ace.testing.immutable_records import (
    InMemoryImmutableRecordStore,
    PreparedLedgerConformanceResult,
    exercise_prepared_ledger_restart,
)
from ace.testing.intelligence_builder import (
    ConnectionAgentReferenceResult,
    FixtureCoreAuthorityResolver,
    FixtureRegisteredSourceOptionProvider,
    FixtureSourceProfile,
    exercise_connection_agent_restart,
    provider_free_source_catalog,
)
from ace.testing.live_source_ingress import (
    LiveSourceIngressConformanceResult,
    exercise_live_source_ingress_restart,
)
from ace.testing.ontology_agent import (
    FixtureConceptModelStrategy,
    OntologyAgentReferenceResult,
    edited_fixture_proposal,
    exercise_ontology_agent_restart,
)
from ace.testing.source_mapping import (
    SourceMappingConformanceResult,
    exercise_prepared_source_mapping,
)
from ace.testing.watch_brief import (
    FixtureBriefingStrategy,
    FixtureIntelligenceModelStrategy,
    WatchBriefReferenceResult,
    edited_fixture_intelligence_model,
    exercise_watch_brief_restart,
    fixture_observations,
)

__all__ = [
    "InMemoryImmutableRecordStore",
    "ConnectionAgentReferenceResult",
    "FixtureCoreAuthorityResolver",
    "FixtureConceptModelStrategy",
    "FixtureBriefingStrategy",
    "FixtureIntelligenceModelStrategy",
    "FixtureRegisteredSourceOptionProvider",
    "FixtureSourceProfile",
    "LiveSourceIngressConformanceResult",
    "OntologyAgentReferenceResult",
    "PreparedLedgerConformanceResult",
    "SourceMappingConformanceResult",
    "WatchBriefReferenceResult",
    "exercise_live_source_ingress_restart",
    "exercise_ontology_agent_restart",
    "exercise_connection_agent_restart",
    "exercise_prepared_ledger_restart",
    "exercise_prepared_source_mapping",
    "exercise_watch_brief_restart",
    "conformance_receipt_json",
    "run_domain_pack_conformance",
    "provider_free_source_catalog",
    "edited_fixture_proposal",
    "edited_fixture_intelligence_model",
    "fixture_observations",
]
