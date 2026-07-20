-- schema/v116_insight_provenance.surql

-- Structured provenance & trust (Phase 2a). source_kind/source_ref structure the
-- opaque source_domain string; trust is the composable posterior (prior(kind) in
-- 2a). All option<...> — legacy rows are NULL until the provenance_reconciler
-- populates them (insight is SCHEMAFULL; see insight-record-contract.md).
-- Indexed for future trust-ranked / kind-filtered retrieval.

DEFINE FIELD source_kind ON TABLE insight TYPE option<string>;
DEFINE FIELD source_ref  ON TABLE insight TYPE option<string>;
DEFINE FIELD trust       ON TABLE insight TYPE option<float>;
DEFINE INDEX insight_source_kind ON TABLE insight FIELDS source_kind;
DEFINE INDEX insight_trust       ON TABLE insight FIELDS trust;
