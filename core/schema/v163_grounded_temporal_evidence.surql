-- TP2: Core-owned, product-scoped grounded temporal evidence substrate.
--
-- This is a separate append-only plane.  It intentionally does not alter or
-- backfill observation, insight, relationship, or synthesis tables.

DEFINE TABLE IF NOT EXISTS grounded_source SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_entity SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_alias SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_claim SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_event SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_event_participant SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_evidence_relation SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_extraction_failure SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_supersession SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_ingestion_item_receipt SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_batch_ingestion_receipt SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;

-- Every semantic table exposes the same exact-replay and lineage query fields.
DEFINE FIELD IF NOT EXISTS contract_version ON grounded_source TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_source TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_source TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON grounded_source TYPE string;
DEFINE FIELD IF NOT EXISTS external_id ON grounded_source TYPE string;
DEFINE FIELD IF NOT EXISTS source_external_id ON grounded_source TYPE string;
DEFINE FIELD IF NOT EXISTS source_version ON grounded_source TYPE string;
DEFINE FIELD IF NOT EXISTS local_id ON grounded_source TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON grounded_source TYPE string;
DEFINE FIELD IF NOT EXISTS idempotency_key ON grounded_source TYPE string;
DEFINE FIELD IF NOT EXISTS supersedes ON grounded_source TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS degraded_reasons ON grounded_source TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS published_at ON grounded_source TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS ingested_at ON grounded_source TYPE datetime;
DEFINE FIELD IF NOT EXISTS extracted_at ON grounded_source TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS payload ON grounded_source TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_source TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_entity TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_entity TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_entity TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON grounded_entity TYPE string;
DEFINE FIELD IF NOT EXISTS external_id ON grounded_entity TYPE string;
DEFINE FIELD IF NOT EXISTS source_external_id ON grounded_entity TYPE string;
DEFINE FIELD IF NOT EXISTS source_version ON grounded_entity TYPE string;
DEFINE FIELD IF NOT EXISTS local_id ON grounded_entity TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON grounded_entity TYPE string;
DEFINE FIELD IF NOT EXISTS idempotency_key ON grounded_entity TYPE string;
DEFINE FIELD IF NOT EXISTS supersedes ON grounded_entity TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS degraded_reasons ON grounded_entity TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS published_at ON grounded_entity TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS ingested_at ON grounded_entity TYPE datetime;
DEFINE FIELD IF NOT EXISTS extracted_at ON grounded_entity TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS payload ON grounded_entity TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_entity TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_alias TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS external_id ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS source_external_id ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS source_version ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS local_id ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS idempotency_key ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS supersedes ON grounded_alias TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS degraded_reasons ON grounded_alias TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS published_at ON grounded_alias TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS ingested_at ON grounded_alias TYPE datetime;
DEFINE FIELD IF NOT EXISTS extracted_at ON grounded_alias TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS entity ON grounded_alias TYPE record<grounded_entity>;
DEFINE FIELD IF NOT EXISTS raw_surface_form ON grounded_alias TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_alias TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_alias TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_claim TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_claim TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_claim TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON grounded_claim TYPE string;
DEFINE FIELD IF NOT EXISTS external_id ON grounded_claim TYPE string;
DEFINE FIELD IF NOT EXISTS source_external_id ON grounded_claim TYPE string;
DEFINE FIELD IF NOT EXISTS source_version ON grounded_claim TYPE string;
DEFINE FIELD IF NOT EXISTS local_id ON grounded_claim TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON grounded_claim TYPE string;
DEFINE FIELD IF NOT EXISTS idempotency_key ON grounded_claim TYPE string;
DEFINE FIELD IF NOT EXISTS supersedes ON grounded_claim TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS degraded_reasons ON grounded_claim TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS published_at ON grounded_claim TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS ingested_at ON grounded_claim TYPE datetime;
DEFINE FIELD IF NOT EXISTS extracted_at ON grounded_claim TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS entity_ids ON grounded_claim TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_claim TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_claim TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_event TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_event TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_event TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON grounded_event TYPE string;
DEFINE FIELD IF NOT EXISTS external_id ON grounded_event TYPE string;
DEFINE FIELD IF NOT EXISTS source_external_id ON grounded_event TYPE string;
DEFINE FIELD IF NOT EXISTS source_version ON grounded_event TYPE string;
DEFINE FIELD IF NOT EXISTS local_id ON grounded_event TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON grounded_event TYPE string;
DEFINE FIELD IF NOT EXISTS idempotency_key ON grounded_event TYPE string;
DEFINE FIELD IF NOT EXISTS supersedes ON grounded_event TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS degraded_reasons ON grounded_event TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS published_at ON grounded_event TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS ingested_at ON grounded_event TYPE datetime;
DEFINE FIELD IF NOT EXISTS extracted_at ON grounded_event TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS payload ON grounded_event TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_event TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_event_participant TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_event_participant TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_event_participant TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON grounded_event_participant TYPE string;
DEFINE FIELD IF NOT EXISTS external_id ON grounded_event_participant TYPE string;
DEFINE FIELD IF NOT EXISTS source_external_id ON grounded_event_participant TYPE string;
DEFINE FIELD IF NOT EXISTS source_version ON grounded_event_participant TYPE string;
DEFINE FIELD IF NOT EXISTS local_id ON grounded_event_participant TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON grounded_event_participant TYPE string;
DEFINE FIELD IF NOT EXISTS idempotency_key ON grounded_event_participant TYPE string;
DEFINE FIELD IF NOT EXISTS supersedes ON grounded_event_participant TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS degraded_reasons ON grounded_event_participant TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS published_at ON grounded_event_participant TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS ingested_at ON grounded_event_participant TYPE datetime;
DEFINE FIELD IF NOT EXISTS extracted_at ON grounded_event_participant TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS event ON grounded_event_participant TYPE record<grounded_event>;
DEFINE FIELD IF NOT EXISTS entity ON grounded_event_participant TYPE record<grounded_entity>;
DEFINE FIELD IF NOT EXISTS payload ON grounded_event_participant TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_event_participant TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_evidence_relation TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS external_id ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS source_external_id ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS source_version ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS local_id ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS idempotency_key ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS supersedes ON grounded_evidence_relation TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS degraded_reasons ON grounded_evidence_relation TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS published_at ON grounded_evidence_relation TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS ingested_at ON grounded_evidence_relation TYPE datetime;
DEFINE FIELD IF NOT EXISTS extracted_at ON grounded_evidence_relation TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS relation ON grounded_evidence_relation TYPE string
    ASSERT $value INSIDE ['mentions', 'participates_in', 'precedes', 'reacts_to', 'co_occurs'];
DEFINE FIELD IF NOT EXISTS subject_ref ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS object_ref ON grounded_evidence_relation TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_evidence_relation TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_evidence_relation TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_extraction_failure TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS external_id ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS source_external_id ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS source_version ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS local_id ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS idempotency_key ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS supersedes ON grounded_extraction_failure TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS degraded_reasons ON grounded_extraction_failure TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS published_at ON grounded_extraction_failure TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS ingested_at ON grounded_extraction_failure TYPE datetime;
DEFINE FIELD IF NOT EXISTS extracted_at ON grounded_extraction_failure TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS failure_code ON grounded_extraction_failure TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_extraction_failure TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_extraction_failure TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_supersession TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_supersession TYPE record<product>;
DEFINE FIELD IF NOT EXISTS lineage_id ON grounded_supersession TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON grounded_supersession TYPE string;
DEFINE FIELD IF NOT EXISTS successor_ref ON grounded_supersession TYPE string;
DEFINE FIELD IF NOT EXISTS predecessor_ref ON grounded_supersession TYPE string;
DEFINE FIELD IF NOT EXISTS source_external_id ON grounded_supersession TYPE string;
DEFINE FIELD IF NOT EXISTS local_id ON grounded_supersession TYPE string;
DEFINE FIELD IF NOT EXISTS policy_version ON grounded_supersession TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_supersession TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_supersession TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_ingestion_item_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_ingestion_item_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS receipt_id ON grounded_ingestion_item_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS manifest_id ON grounded_ingestion_item_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS item_key ON grounded_ingestion_item_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS item_ordinal ON grounded_ingestion_item_receipt TYPE int;
DEFINE FIELD IF NOT EXISTS input_hash ON grounded_ingestion_item_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS disposition ON grounded_ingestion_item_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_ingestion_item_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_ingestion_item_receipt TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_batch_ingestion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_batch_ingestion_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS receipt_id ON grounded_batch_ingestion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS manifest_id ON grounded_batch_ingestion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS manifest_hash ON grounded_batch_ingestion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS adapter_id ON grounded_batch_ingestion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS extraction_run_id ON grounded_batch_ingestion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_batch_ingestion_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_batch_ingestion_receipt TYPE datetime DEFAULT time::now();

-- Exact replay, lineage, isolation, and manifest reconciliation indexes.
DEFINE INDEX IF NOT EXISTS idx_grounded_source_exact ON grounded_source FIELDS product, idempotency_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_source_lineage ON grounded_source FIELDS product, source_external_id, source_version, local_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_entity_exact ON grounded_entity FIELDS product, idempotency_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_entity_lineage ON grounded_entity FIELDS product, source_external_id, source_version, local_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_alias_exact ON grounded_alias FIELDS product, idempotency_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_alias_entity ON grounded_alias FIELDS product, entity, raw_surface_form;
DEFINE INDEX IF NOT EXISTS idx_grounded_claim_exact ON grounded_claim FIELDS product, idempotency_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_claim_lineage ON grounded_claim FIELDS product, source_external_id, source_version, local_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_event_exact ON grounded_event FIELDS product, idempotency_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_event_lineage ON grounded_event FIELDS product, source_external_id, source_version, local_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_participant_exact ON grounded_event_participant FIELDS product, idempotency_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_relation_exact ON grounded_evidence_relation FIELDS product, idempotency_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_failure_exact ON grounded_extraction_failure FIELDS product, idempotency_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_failure_query ON grounded_extraction_failure FIELDS product, failure_code, source_external_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_supersession_exact ON grounded_supersession FIELDS product, lineage_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_supersession_successor ON grounded_supersession FIELDS product, successor_ref, predecessor_ref UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_supersession_lineage ON grounded_supersession FIELDS product, record_kind, source_external_id, local_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_item_receipt_exact ON grounded_ingestion_item_receipt FIELDS product, receipt_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_item_manifest ON grounded_ingestion_item_receipt FIELDS product, manifest_id, item_ordinal UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_batch_receipt_exact ON grounded_batch_ingestion_receipt FIELDS product, receipt_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_batch_manifest ON grounded_batch_ingestion_receipt FIELDS product, manifest_id UNIQUE;
