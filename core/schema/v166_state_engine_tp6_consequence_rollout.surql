-- TP6: append-only product-scoped evidence queries, consequence rollouts, use, and reconciliation.

DEFINE TABLE IF NOT EXISTS grounded_evidence_query SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_reasoning_evidence_pack SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_rollout_proposal SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_rollout_execution SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_model_branch_proposal SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_rollout_challenge SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_consequence_rollout SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_rollout_reasoning_use SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_rollout_outcome SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE TABLE IF NOT EXISTS grounded_rollout_reconciliation SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_evidence_query TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_evidence_query TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_evidence_query TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_evidence_query TYPE string;
DEFINE FIELD IF NOT EXISTS task_id ON grounded_evidence_query TYPE string;
DEFINE FIELD IF NOT EXISTS invocation_id ON grounded_evidence_query TYPE string;
DEFINE FIELD IF NOT EXISTS as_of ON grounded_evidence_query TYPE datetime;
DEFINE FIELD IF NOT EXISTS payload ON grounded_evidence_query TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_evidence_query TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_reasoning_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_reasoning_evidence_pack TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_reasoning_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_reasoning_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS task_id ON grounded_reasoning_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS invocation_id ON grounded_reasoning_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS query_id ON grounded_reasoning_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS evidence_pack_id ON grounded_reasoning_evidence_pack TYPE string;
DEFINE FIELD IF NOT EXISTS evidence_refs ON grounded_reasoning_evidence_pack TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_reasoning_evidence_pack TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_reasoning_evidence_pack TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_rollout_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_rollout_proposal TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_rollout_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_rollout_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS task_id ON grounded_rollout_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS invocation_id ON grounded_rollout_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS rollout_id ON grounded_rollout_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS projection_id ON grounded_rollout_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS transition_revision_ids ON grounded_rollout_proposal TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_rollout_proposal TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_rollout_proposal TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_rollout_execution TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_rollout_execution TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_rollout_execution TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_rollout_execution TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON grounded_rollout_execution TYPE string;
DEFINE FIELD IF NOT EXISTS branch_id ON grounded_rollout_execution TYPE string;
DEFINE FIELD IF NOT EXISTS branch_kind ON grounded_rollout_execution TYPE string;
DEFINE FIELD IF NOT EXISTS projection_id ON grounded_rollout_execution TYPE string;
DEFINE FIELD IF NOT EXISTS transition_revision_ids ON grounded_rollout_execution TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_rollout_execution TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_rollout_execution TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_model_branch_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_model_branch_proposal TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_model_branch_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_model_branch_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON grounded_model_branch_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS branch_ids ON grounded_model_branch_proposal TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_model_branch_proposal TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_model_branch_proposal TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_rollout_challenge TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_rollout_challenge TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_rollout_challenge TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_rollout_challenge TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON grounded_rollout_challenge TYPE string;
DEFINE FIELD IF NOT EXISTS completed ON grounded_rollout_challenge TYPE bool;
DEFINE FIELD IF NOT EXISTS transition_revision_ids ON grounded_rollout_challenge TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_rollout_challenge TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_rollout_challenge TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_consequence_rollout TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_consequence_rollout TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_consequence_rollout TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_consequence_rollout TYPE string;
DEFINE FIELD IF NOT EXISTS task_id ON grounded_consequence_rollout TYPE string;
DEFINE FIELD IF NOT EXISTS invocation_id ON grounded_consequence_rollout TYPE string;
DEFINE FIELD IF NOT EXISTS rollout_id ON grounded_consequence_rollout TYPE string;
DEFINE FIELD IF NOT EXISTS revision ON grounded_consequence_rollout TYPE int;
DEFINE FIELD IF NOT EXISTS projection_id ON grounded_consequence_rollout TYPE string;
DEFINE FIELD IF NOT EXISTS disposition ON grounded_consequence_rollout TYPE string;
DEFINE FIELD IF NOT EXISTS transition_revision_ids ON grounded_consequence_rollout TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS payload ON grounded_consequence_rollout TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_consequence_rollout TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_rollout_reasoning_use TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_rollout_reasoning_use TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_rollout_reasoning_use TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_rollout_reasoning_use TYPE string;
DEFINE FIELD IF NOT EXISTS task_id ON grounded_rollout_reasoning_use TYPE string;
DEFINE FIELD IF NOT EXISTS invocation_id ON grounded_rollout_reasoning_use TYPE string;
DEFINE FIELD IF NOT EXISTS rollout_revision_id ON grounded_rollout_reasoning_use TYPE string;
DEFINE FIELD IF NOT EXISTS comparison_state ON grounded_rollout_reasoning_use TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_rollout_reasoning_use TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_rollout_reasoning_use TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_rollout_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_rollout_outcome TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_rollout_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_rollout_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS rollout_revision_id ON grounded_rollout_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS predicted_outcome_id ON grounded_rollout_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS branch_id ON grounded_rollout_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS observed_at ON grounded_rollout_outcome TYPE datetime;
DEFINE FIELD IF NOT EXISTS evidence_pack_id ON grounded_rollout_outcome TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON grounded_rollout_outcome TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_rollout_outcome TYPE datetime DEFAULT time::now();

DEFINE FIELD IF NOT EXISTS contract_version ON grounded_rollout_reconciliation TYPE string;
DEFINE FIELD IF NOT EXISTS product ON grounded_rollout_reconciliation TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON grounded_rollout_reconciliation TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON grounded_rollout_reconciliation TYPE string;
DEFINE FIELD IF NOT EXISTS rollout_revision_id ON grounded_rollout_reconciliation TYPE string;
DEFINE FIELD IF NOT EXISTS predicted_outcome_id ON grounded_rollout_reconciliation TYPE string;
DEFINE FIELD IF NOT EXISTS observation_id ON grounded_rollout_reconciliation TYPE string;
DEFINE FIELD IF NOT EXISTS branch_id ON grounded_rollout_reconciliation TYPE string;
DEFINE FIELD IF NOT EXISTS disposition ON grounded_rollout_reconciliation TYPE string;
DEFINE FIELD IF NOT EXISTS reconciled_at ON grounded_rollout_reconciliation TYPE datetime;
DEFINE FIELD IF NOT EXISTS payload ON grounded_rollout_reconciliation TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON grounded_rollout_reconciliation TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_grounded_evidence_query_exact ON grounded_evidence_query
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_evidence_query_task ON grounded_evidence_query
    FIELDS product, task_id, invocation_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_reasoning_evidence_pack_exact ON grounded_reasoning_evidence_pack
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_reasoning_evidence_pack_task ON grounded_reasoning_evidence_pack
    FIELDS product, task_id, invocation_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_rollout_proposal_exact ON grounded_rollout_proposal
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_rollout_execution_exact ON grounded_rollout_execution
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_model_branch_proposal_exact ON grounded_model_branch_proposal
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_rollout_challenge_exact ON grounded_rollout_challenge
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_consequence_rollout_exact ON grounded_consequence_rollout
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_consequence_rollout_revision ON grounded_consequence_rollout
    FIELDS product, rollout_id, revision UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_consequence_rollout_task ON grounded_consequence_rollout
    FIELDS product, task_id, invocation_id;
DEFINE INDEX IF NOT EXISTS idx_grounded_rollout_reasoning_use_exact ON grounded_rollout_reasoning_use
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_rollout_outcome_exact ON grounded_rollout_outcome
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_rollout_outcome_revision ON grounded_rollout_outcome
    FIELDS product, rollout_revision_id, observed_at;
DEFINE INDEX IF NOT EXISTS idx_grounded_rollout_reconciliation_exact ON grounded_rollout_reconciliation
    FIELDS product, stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_grounded_rollout_reconciliation_revision ON grounded_rollout_reconciliation
    FIELDS product, rollout_revision_id, reconciled_at;
