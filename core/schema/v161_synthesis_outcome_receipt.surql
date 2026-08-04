-- TP1A: truthful, product-scoped observation synthesis outcomes.
--
-- Existing observation rows are intentionally not backfilled.  A historical
-- `status = 'processed'` row without a trustworthy receipt remains queryable as
-- `legacy_unexplained`; this migration adds structure, never reconstructed facts.

DEFINE TABLE IF NOT EXISTS synthesis_outcome_receipt SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE FIELD IF NOT EXISTS contract_version ON synthesis_outcome_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON synthesis_outcome_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS observation ON synthesis_outcome_receipt TYPE record<observation>;
DEFINE FIELD IF NOT EXISTS attempt_id ON synthesis_outcome_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS attempt_count ON synthesis_outcome_receipt TYPE int;
DEFINE FIELD IF NOT EXISTS processing_state ON synthesis_outcome_receipt TYPE string
    ASSERT $value INSIDE ['pending', 'processing', 'succeeded', 'retryable_failed', 'dead_letter'];
DEFINE FIELD IF NOT EXISTS disposition ON synthesis_outcome_receipt TYPE option<string>
    ASSERT $value = NONE OR $value INSIDE ['insight_created', 'insight_updated', 'insight_merged', 'conflict_preserved', 'skipped'];
DEFINE FIELD IF NOT EXISTS created_insights ON synthesis_outcome_receipt TYPE array<record<insight>> DEFAULT [];
DEFINE FIELD IF NOT EXISTS updated_insights ON synthesis_outcome_receipt TYPE array<record<insight>> DEFAULT [];
DEFINE FIELD IF NOT EXISTS merged_insights ON synthesis_outcome_receipt TYPE array<record<insight>> DEFAULT [];
DEFINE FIELD IF NOT EXISTS conflicting_insights ON synthesis_outcome_receipt TYPE array<record<insight>> DEFAULT [];
DEFINE FIELD IF NOT EXISTS conflict_records ON synthesis_outcome_receipt TYPE array<record<conflict>> DEFAULT [];
DEFINE FIELD IF NOT EXISTS reason ON synthesis_outcome_receipt TYPE option<string>;
DEFINE FIELD IF NOT EXISTS failure ON synthesis_outcome_receipt TYPE option<object> FLEXIBLE;
DEFINE FIELD IF NOT EXISTS retryable ON synthesis_outcome_receipt TYPE bool;
DEFINE FIELD IF NOT EXISTS next_retry_at ON synthesis_outcome_receipt TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS processor_version ON synthesis_outcome_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS policy_version ON synthesis_outcome_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS schema_version ON synthesis_outcome_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON synthesis_outcome_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS started_at ON synthesis_outcome_receipt TYPE datetime;
DEFINE FIELD IF NOT EXISTS completed_at ON synthesis_outcome_receipt TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS provenance ON synthesis_outcome_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS explainable_terminal ON synthesis_outcome_receipt TYPE bool;
DEFINE FIELD IF NOT EXISTS receipt ON synthesis_outcome_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS receipt_hash ON synthesis_outcome_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS created_at ON synthesis_outcome_receipt TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS idx_synthesis_receipt_attempt ON synthesis_outcome_receipt FIELDS product, attempt_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_synthesis_receipt_observation ON synthesis_outcome_receipt FIELDS product, observation, completed_at;
DEFINE INDEX IF NOT EXISTS idx_synthesis_receipt_health ON synthesis_outcome_receipt FIELDS product, processing_state, disposition, completed_at;

DEFINE FIELD IF NOT EXISTS processing_state ON observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS processing_attempt_count ON observation TYPE option<int>;
DEFINE FIELD IF NOT EXISTS processing_started_at ON observation TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS next_retry_at ON observation TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS outcome_receipt ON observation TYPE option<record<synthesis_outcome_receipt>>;
DEFINE FIELD IF NOT EXISTS processing_route ON observation TYPE option<string>;
DEFINE INDEX IF NOT EXISTS idx_observation_processing_queue ON observation
    FIELDS product, processing_state, next_retry_at, created_at;
DEFINE INDEX IF NOT EXISTS idx_observation_outcome ON observation FIELDS product, outcome_receipt;

-- Exact retries of an embedding-dedupe merge must not boost confidence twice.
DEFINE FIELD IF NOT EXISTS synthesis_merge_attempts ON insight TYPE option<array<string>>;
