-- TP4: product-scoped reviewed assertions and versioned belief-state projection.
-- Existing unscoped assertion rows are not backfilled or made operational by
-- this migration.  New Core writers always set product and product-fenced
-- readers ignore legacy rows without it.

DEFINE FIELD IF NOT EXISTS product ON relationship_proposal TYPE option<record<product>>;
DEFINE FIELD IF NOT EXISTS source_origin_ids ON relationship_proposal TYPE array<string> DEFAULT [];

DEFINE FIELD IF NOT EXISTS product ON relationship_assertion TYPE option<record<product>>;
DEFINE FIELD IF NOT EXISTS review_refs ON relationship_assertion TYPE array<string> DEFAULT [];

DEFINE FIELD IF NOT EXISTS product ON assertion_review TYPE option<record<product>>;
DEFINE FIELD IF NOT EXISTS authority ON assertion_review TYPE option<string>;
DEFINE FIELD IF NOT EXISTS review_ref ON assertion_review TYPE option<string>;
DEFINE FIELD IF NOT EXISTS reviewed_material_hash ON assertion_review TYPE option<string>;
DEFINE FIELD IF NOT EXISTS counterevidence_search_ref ON assertion_review TYPE option<string>;
DEFINE FIELD IF NOT EXISTS counterevidence_complete ON assertion_review TYPE bool DEFAULT false;

DEFINE FIELD IF NOT EXISTS product ON assertion_event TYPE option<record<product>>;
DEFINE FIELD IF NOT EXISTS product ON assertion_dependency TYPE option<record<product>>;

DEFINE FIELD IF NOT EXISTS product ON operational_relationship TYPE option<record<product>>;
DEFINE FIELD IF NOT EXISTS evidence_refs ON operational_relationship TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS review_refs ON operational_relationship TYPE array<string> DEFAULT [];
DEFINE INDEX OVERWRITE idx_operational_endpoints ON operational_relationship
    FIELDS product, in, out, predicate UNIQUE;

DEFINE INDEX IF NOT EXISTS idx_relationship_proposal_product ON relationship_proposal
    FIELDS product, subject, predicate, object;
DEFINE INDEX IF NOT EXISTS idx_relationship_assertion_product ON relationship_assertion
    FIELDS product, status, projection_eligible;
DEFINE INDEX IF NOT EXISTS idx_assertion_review_product ON assertion_review
    FIELDS product, target_assertion;
DEFINE INDEX IF NOT EXISTS idx_assertion_event_product ON assertion_event
    FIELDS product, assertion_id, created_at;
DEFINE INDEX IF NOT EXISTS idx_assertion_dependency_product ON assertion_dependency
    FIELDS product, in, out, dependency_type;
DEFINE INDEX IF NOT EXISTS idx_operational_product ON operational_relationship
    FIELDS product, assertion_id;

DEFINE TABLE IF NOT EXISTS grounded_epistemic_proposal SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_assertion_review_v1 SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_epistemic_assertion_revision SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_counterevidence_search SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_evidence_pack SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_belief_projection SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_external_insight SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_inference_receipt SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_reprojection_receipt SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_epistemic_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_epistemic_proposal TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_epistemic_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_epistemic_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS assertion_id ON grounded_epistemic_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS evidence_refs ON grounded_epistemic_proposal TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_epistemic_proposal TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_epistemic_proposal TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_assertion_review_v1 TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_assertion_review_v1 TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_assertion_review_v1 TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_assertion_review_v1 TYPE string;
DEFINE FIELD IF NOT EXISTS assertion_id ON grounded_assertion_review_v1 TYPE string;
DEFINE FIELD IF NOT EXISTS disposition ON grounded_assertion_review_v1 TYPE string;
DEFINE FIELD IF NOT EXISTS authority ON grounded_assertion_review_v1 TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_assertion_review_v1 TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_assertion_review_v1 TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_epistemic_assertion_revision TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_epistemic_assertion_revision TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_epistemic_assertion_revision TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_epistemic_assertion_revision TYPE string;
DEFINE FIELD IF NOT EXISTS assertion_id ON grounded_epistemic_assertion_revision TYPE string;
DEFINE FIELD IF NOT EXISTS revision ON grounded_epistemic_assertion_revision TYPE int;
DEFINE FIELD IF NOT EXISTS disposition ON grounded_epistemic_assertion_revision TYPE string;
DEFINE FIELD IF NOT EXISTS dependency_refs ON grounded_epistemic_assertion_revision TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS prior_revision_ref ON grounded_epistemic_assertion_revision TYPE option<string>;
DEFINE FIELD IF NOT EXISTS payload ON grounded_epistemic_assertion_revision TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_epistemic_assertion_revision TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_counterevidence_search TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_counterevidence_search TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_counterevidence_search TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_counterevidence_search TYPE string;
DEFINE FIELD IF NOT EXISTS assertion_material_hash ON grounded_counterevidence_search TYPE string;
DEFINE FIELD IF NOT EXISTS completed ON grounded_counterevidence_search TYPE bool;
DEFINE FIELD IF NOT EXISTS payload ON grounded_counterevidence_search TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_counterevidence_search TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_evidence_pack TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS as_of ON grounded_evidence_pack TYPE datetime;
DEFINE FIELD IF NOT EXISTS candidate_receipt_id ON grounded_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS evidence_refs ON grounded_evidence_pack TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_evidence_pack TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_evidence_pack TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_belief_projection TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_belief_projection TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_belief_projection TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_belief_projection TYPE string;
DEFINE FIELD IF NOT EXISTS as_of ON grounded_belief_projection TYPE datetime;
DEFINE FIELD IF NOT EXISTS revision ON grounded_belief_projection TYPE int;
DEFINE FIELD IF NOT EXISTS evidence_pack_id ON grounded_belief_projection TYPE string;
DEFINE FIELD IF NOT EXISTS assertion_refs ON grounded_belief_projection TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_belief_projection TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_belief_projection TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_external_insight TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_external_insight TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_external_insight TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_external_insight TYPE string;
DEFINE FIELD IF NOT EXISTS as_of ON grounded_external_insight TYPE datetime;
DEFINE FIELD IF NOT EXISTS evidence_pack_id ON grounded_external_insight TYPE string;
DEFINE FIELD IF NOT EXISTS inference_receipt_id ON grounded_external_insight TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_external_insight TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_external_insight TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_inference_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_inference_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_inference_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_inference_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS evidence_pack_id ON grounded_inference_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS assertion_refs ON grounded_inference_receipt TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_inference_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_inference_receipt TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_reprojection_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_reprojection_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_reprojection_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_reprojection_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS prior_projection_id ON grounded_reprojection_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS resulting_projection_id ON grounded_reprojection_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS affected_assertion_refs ON grounded_reprojection_receipt TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_reprojection_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_reprojection_receipt TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_grounded_epistemic_proposal_exact ON grounded_epistemic_proposal
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_epistemic_proposal_assertion ON grounded_epistemic_proposal
    FIELDS product, assertion_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_assertion_review_exact ON grounded_assertion_review_v1
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_assertion_review_assertion ON grounded_assertion_review_v1
    FIELDS product, assertion_id, disposition;
DEFINE INDEX IF NOT EXISTS idx_grounded_assertion_revision_exact ON grounded_epistemic_assertion_revision
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_assertion_revision_assertion ON grounded_epistemic_assertion_revision
    FIELDS product, assertion_id, revision;
DEFINE INDEX IF NOT EXISTS idx_grounded_counterevidence_exact ON grounded_counterevidence_search
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_evidence_pack_exact ON grounded_evidence_pack
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_belief_projection_exact ON grounded_belief_projection
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_belief_projection_asof ON grounded_belief_projection
    FIELDS product, as_of, revision;
DEFINE INDEX IF NOT EXISTS idx_grounded_external_insight_exact ON grounded_external_insight
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_inference_receipt_exact ON grounded_inference_receipt
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_reprojection_receipt_exact ON grounded_reprojection_receipt
    FIELDS product, stable_id UNIQUE;
