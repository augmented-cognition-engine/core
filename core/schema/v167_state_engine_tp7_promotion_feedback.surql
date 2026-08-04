-- TP7: explicit, append-only promotion review and existing-memory lineage.

DEFINE TABLE IF NOT EXISTS grounded_promotion_proposal SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_promotion_review SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_promotion_receipt SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_promotion_memory_lineage SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_promotion_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_promotion_proposal TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_promotion_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_promotion_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS task_id ON grounded_promotion_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS target_kind ON grounded_promotion_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON grounded_promotion_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS evidence_pack_id ON grounded_promotion_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS rollout_revision_id ON grounded_promotion_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS proposed_at ON grounded_promotion_proposal TYPE datetime;
DEFINE FIELD IF NOT EXISTS payload ON grounded_promotion_proposal TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_promotion_proposal TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_promotion_review TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_promotion_review TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_promotion_review TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_promotion_review TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON grounded_promotion_review TYPE string;
DEFINE FIELD IF NOT EXISTS disposition ON grounded_promotion_review TYPE string;
DEFINE FIELD IF NOT EXISTS authority ON grounded_promotion_review TYPE string;
DEFINE FIELD IF NOT EXISTS reviewed_at ON grounded_promotion_review TYPE datetime;
DEFINE FIELD IF NOT EXISTS payload ON grounded_promotion_review TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_promotion_review TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_promotion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_promotion_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_promotion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_promotion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON grounded_promotion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS review_id ON grounded_promotion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS disposition ON grounded_promotion_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS memory_id ON grounded_promotion_receipt TYPE option<string>;
DEFINE FIELD IF NOT EXISTS supersedes_receipt_ids ON grounded_promotion_receipt TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS invalidates_receipt_ids ON grounded_promotion_receipt TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS contests_receipt_ids ON grounded_promotion_receipt TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS expires_at ON grounded_promotion_receipt TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS effective_at ON grounded_promotion_receipt TYPE datetime;
DEFINE FIELD IF NOT EXISTS payload ON grounded_promotion_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_promotion_receipt TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_promotion_memory_lineage TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_promotion_memory_lineage TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_promotion_memory_lineage TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_promotion_memory_lineage TYPE string;
DEFINE FIELD IF NOT EXISTS memory_id ON grounded_promotion_memory_lineage TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON grounded_promotion_memory_lineage TYPE string;
DEFINE FIELD IF NOT EXISTS receipt_id ON grounded_promotion_memory_lineage TYPE string;
DEFINE FIELD IF NOT EXISTS task_id ON grounded_promotion_memory_lineage TYPE string;
DEFINE FIELD IF NOT EXISTS evidence_pack_id ON grounded_promotion_memory_lineage TYPE string;
DEFINE FIELD IF NOT EXISTS rollout_revision_id ON grounded_promotion_memory_lineage TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_promotion_memory_lineage TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_promotion_memory_lineage TYPE datetime;

DEFINE INDEX IF NOT EXISTS idx_grounded_promotion_proposal_exact ON grounded_promotion_proposal
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_promotion_proposal_task ON grounded_promotion_proposal
    FIELDS product, task_id, proposed_at;
DEFINE INDEX IF NOT EXISTS idx_grounded_promotion_review_exact ON grounded_promotion_review
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_promotion_review_proposal ON grounded_promotion_review
    FIELDS product, proposal_id, reviewed_at;
DEFINE INDEX IF NOT EXISTS idx_grounded_promotion_receipt_exact ON grounded_promotion_receipt
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_promotion_receipt_proposal ON grounded_promotion_receipt
    FIELDS product, proposal_id, effective_at;
DEFINE INDEX IF NOT EXISTS idx_grounded_promotion_memory_lineage_exact ON grounded_promotion_memory_lineage
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_promotion_memory_lineage_memory ON grounded_promotion_memory_lineage
    FIELDS product, memory_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_promotion_memory_lineage_receipt ON grounded_promotion_memory_lineage
    FIELDS product, receipt_id UNIQUE;

-- The cognitive-memory row remains the existing insight record. These fields
-- add exact TP7 lineage without mutating or backfilling any prior memory.
DEFINE FIELD IF NOT EXISTS promotion_contract_version ON insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS promotion_receipt_id ON insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS promotion_receipt_hash ON insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS promotion_proposal_id ON insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS promotion_material_hash ON insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS promotion_evidence_pack_id ON insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS promotion_evidence_pack_hash ON insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS promotion_task_id ON insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS promotion_decision_receipt_id ON insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS promotion_lineage_id ON insight TYPE option<string>;
DEFINE INDEX IF NOT EXISTS idx_insight_promotion_receipt ON insight FIELDS product, promotion_receipt_id;

