-- TP8: append-only product lifecycle and operational recovery evidence.

-- Additive query projection fields for bounded large-corpus preselection. The
-- authoritative immutable payload and identity remain owned by TP2.
DEFINE FIELD IF NOT EXISTS title ON grounded_source TYPE option<string>;
DEFINE FIELD IF NOT EXISTS canonical_name ON grounded_entity TYPE option<string>;
DEFINE FIELD IF NOT EXISTS raw_surface_form ON grounded_alias TYPE option<string>;
DEFINE FIELD IF NOT EXISTS claim_text ON grounded_claim TYPE option<string>;
DEFINE FIELD IF NOT EXISTS predicate ON grounded_claim TYPE option<string>;
DEFINE FIELD IF NOT EXISTS event_description ON grounded_event TYPE option<string>;
DEFINE FIELD IF NOT EXISTS relation_basis ON grounded_evidence_relation TYPE option<string>;

DEFINE INDEX IF NOT EXISTS idx_grounded_claim_product_predicate ON grounded_claim
    FIELDS product, predicate;
DEFINE INDEX IF NOT EXISTS idx_grounded_claim_product_source ON grounded_claim
    FIELDS product, source_external_id;
-- TP8's bounded item preflight and version reconciliation use these exact
-- product-scoped coordinates.  The v163 lineage indexes placed source_version
-- before local_id, which is not selective for a query that must see all
-- versions of one source coordinate.
DEFINE INDEX IF NOT EXISTS idx_grounded_source_product_stable ON grounded_source
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_entity_product_stable ON grounded_entity
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_alias_product_stable ON grounded_alias
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_claim_product_stable ON grounded_claim
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_event_product_stable ON grounded_event
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_event_participant_product_stable ON grounded_event_participant
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_relation_product_stable ON grounded_evidence_relation
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_failure_product_stable ON grounded_extraction_failure
    FIELDS product, stable_id UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_grounded_source_coordinate ON grounded_source
    FIELDS product, source_external_id, local_id, source_version;
DEFINE INDEX IF NOT EXISTS idx_grounded_entity_coordinate ON grounded_entity
    FIELDS product, source_external_id, local_id, source_version;
DEFINE INDEX IF NOT EXISTS idx_grounded_alias_coordinate ON grounded_alias
    FIELDS product, source_external_id, local_id, source_version;
DEFINE INDEX IF NOT EXISTS idx_grounded_claim_coordinate ON grounded_claim
    FIELDS product, source_external_id, local_id, source_version;
DEFINE INDEX IF NOT EXISTS idx_grounded_event_coordinate ON grounded_event
    FIELDS product, source_external_id, local_id, source_version;
DEFINE INDEX IF NOT EXISTS idx_grounded_event_participant_coordinate ON grounded_event_participant
    FIELDS product, source_external_id, local_id, source_version;
DEFINE INDEX IF NOT EXISTS idx_grounded_relation_coordinate ON grounded_evidence_relation
    FIELDS product, source_external_id, local_id, source_version;
DEFINE INDEX IF NOT EXISTS idx_grounded_failure_coordinate ON grounded_extraction_failure
    FIELDS product, source_external_id, local_id, source_version;

DEFINE TABLE IF NOT EXISTS grounded_product_lifecycle SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE FIELD IF NOT EXISTS contract_version ON grounded_product_lifecycle TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_product_lifecycle TYPE record<product>;
DEFINE FIELD IF NOT EXISTS receipt_id ON grounded_product_lifecycle TYPE string;
DEFINE FIELD IF NOT EXISTS lifecycle_state ON grounded_product_lifecycle TYPE string
    ASSERT $value INSIDE ['active', 'archived'];
DEFINE FIELD IF NOT EXISTS prior_receipt_id ON grounded_product_lifecycle TYPE option<string>;
DEFINE FIELD IF NOT EXISTS actor_ref ON grounded_product_lifecycle TYPE string;
DEFINE FIELD IF NOT EXISTS reason ON grounded_product_lifecycle TYPE string;
DEFINE FIELD IF NOT EXISTS occurred_at ON grounded_product_lifecycle TYPE datetime;
DEFINE FIELD IF NOT EXISTS payload ON grounded_product_lifecycle TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_product_lifecycle TYPE datetime DEFAULT time::now();

DEFINE TABLE IF NOT EXISTS grounded_operational_receipt SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE FIELD IF NOT EXISTS contract_version ON grounded_operational_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_operational_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS receipt_id ON grounded_operational_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS run_id ON grounded_operational_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS operation_id ON grounded_operational_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS operation_kind ON grounded_operational_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS status ON grounded_operational_receipt TYPE string
    ASSERT $value INSIDE ['started', 'completed', 'failed', 'degraded'];
DEFINE FIELD IF NOT EXISTS started_at ON grounded_operational_receipt TYPE datetime;
DEFINE FIELD IF NOT EXISTS finished_at ON grounded_operational_receipt TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_operational_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_operational_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_operational_receipt TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_grounded_product_lifecycle_exact ON grounded_product_lifecycle
    FIELDS product, receipt_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_product_lifecycle_order ON grounded_product_lifecycle
    FIELDS product, occurred_at, receipt_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_operational_receipt_exact ON grounded_operational_receipt
    FIELDS product, receipt_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_operational_receipt_run ON grounded_operational_receipt
    FIELDS product, run_id, operation_id, started_at;
