-- TP5: append-only, product-scoped world-dynamics hypotheses and calibration.

DEFINE TABLE IF NOT EXISTS grounded_transition_proposal SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_transition_challenge SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_transition_review SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_transition_revision SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_transition_branch_input SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_transition_outcome SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_transition_calibration SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_transition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_transition_proposal TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_transition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_transition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS hypothesis_id ON grounded_transition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS projection_id ON grounded_transition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS evidence_pack_id ON grounded_transition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS evidence_refs ON grounded_transition_proposal TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_transition_proposal TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_transition_proposal TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_transition_challenge TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_transition_challenge TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_transition_challenge TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_transition_challenge TYPE string;
DEFINE FIELD IF NOT EXISTS hypothesis_id ON grounded_transition_challenge TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON grounded_transition_challenge TYPE string;
DEFINE FIELD IF NOT EXISTS completed ON grounded_transition_challenge TYPE bool;
DEFINE FIELD IF NOT EXISTS evidence_refs ON grounded_transition_challenge TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_transition_challenge TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_transition_challenge TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_transition_review TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_transition_review TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_transition_review TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_transition_review TYPE string;
DEFINE FIELD IF NOT EXISTS hypothesis_id ON grounded_transition_review TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON grounded_transition_review TYPE string;
DEFINE FIELD IF NOT EXISTS disposition ON grounded_transition_review TYPE string;
DEFINE FIELD IF NOT EXISTS authority ON grounded_transition_review TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_transition_review TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_transition_review TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_transition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_transition_revision TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_transition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_transition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS hypothesis_id ON grounded_transition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS revision ON grounded_transition_revision TYPE int;
DEFINE FIELD IF NOT EXISTS review_state ON grounded_transition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS rollout_eligible ON grounded_transition_revision TYPE bool;
DEFINE FIELD IF NOT EXISTS prior_revision_id ON grounded_transition_revision TYPE option<string>;
DEFINE FIELD IF NOT EXISTS dependency_refs ON grounded_transition_revision TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_transition_revision TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_transition_revision TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_transition_branch_input TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_transition_branch_input TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_transition_branch_input TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_transition_branch_input TYPE string;
DEFINE FIELD IF NOT EXISTS hypothesis_id ON grounded_transition_branch_input TYPE string;
DEFINE FIELD IF NOT EXISTS transition_revision_id ON grounded_transition_branch_input TYPE string;
DEFINE FIELD IF NOT EXISTS projection_id ON grounded_transition_branch_input TYPE string;
DEFINE FIELD IF NOT EXISTS applicable ON grounded_transition_branch_input TYPE bool;
DEFINE FIELD IF NOT EXISTS payload ON grounded_transition_branch_input TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_transition_branch_input TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_transition_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_transition_outcome TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_transition_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_transition_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS hypothesis_id ON grounded_transition_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS transition_revision_id ON grounded_transition_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS disposition ON grounded_transition_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS observed_at ON grounded_transition_outcome TYPE datetime;
DEFINE FIELD IF NOT EXISTS evidence_refs ON grounded_transition_outcome TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS forecast_ref ON grounded_transition_outcome TYPE option<string>;
DEFINE FIELD IF NOT EXISTS forecast_resolution_ref ON grounded_transition_outcome TYPE option<string>;
DEFINE FIELD IF NOT EXISTS payload ON grounded_transition_outcome TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_transition_outcome TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_transition_calibration TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_transition_calibration TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_transition_calibration TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_transition_calibration TYPE string;
DEFINE FIELD IF NOT EXISTS hypothesis_id ON grounded_transition_calibration TYPE string;
DEFINE FIELD IF NOT EXISTS transition_revision_id ON grounded_transition_calibration TYPE string;
DEFINE FIELD IF NOT EXISTS outcome_refs ON grounded_transition_calibration TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS calibrated_at ON grounded_transition_calibration TYPE datetime;
DEFINE FIELD IF NOT EXISTS payload ON grounded_transition_calibration TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_transition_calibration TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_grounded_transition_proposal_exact ON grounded_transition_proposal
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_proposal_hypothesis ON grounded_transition_proposal
    FIELDS product, hypothesis_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_challenge_exact ON grounded_transition_challenge
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_review_exact ON grounded_transition_review
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_revision_exact ON grounded_transition_revision
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_revision_latest ON grounded_transition_revision
    FIELDS product, hypothesis_id, revision UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_revision_lookup ON grounded_transition_revision
    FIELDS product, review_state, rollout_eligible;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_branch_input_exact ON grounded_transition_branch_input
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_outcome_exact ON grounded_transition_outcome
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_outcome_revision ON grounded_transition_outcome
    FIELDS product, transition_revision_id, observed_at;
DEFINE INDEX IF NOT EXISTS idx_grounded_transition_calibration_exact ON grounded_transition_calibration
    FIELDS product, stable_id UNIQUE;
