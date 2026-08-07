-- Domain-neutral Core state admission: immutable opaque revisions, one exact
-- product-scoped head, durable commit receipts, and append-only audit identity.

DEFINE TABLE IF NOT EXISTS governed_state_revision SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE governed_state_revision TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE governed_state_revision TYPE record<product>;
DEFINE FIELD IF NOT EXISTS state_kind ON TABLE governed_state_revision TYPE string;
DEFINE FIELD IF NOT EXISTS state_id ON TABLE governed_state_revision TYPE string;
DEFINE FIELD IF NOT EXISTS sequence ON TABLE governed_state_revision TYPE int;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE governed_state_revision TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON TABLE governed_state_revision TYPE string;
DEFINE FIELD IF NOT EXISTS prior_revision_id ON TABLE governed_state_revision TYPE option<string>;
DEFINE FIELD IF NOT EXISTS payload_contract ON TABLE governed_state_revision TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE governed_state_revision TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE governed_state_revision TYPE datetime;
DEFINE INDEX IF NOT EXISTS governed_state_revision_stable ON TABLE governed_state_revision FIELDS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS governed_state_revision_lineage ON TABLE governed_state_revision FIELDS product, state_kind, state_id, sequence UNIQUE;

DEFINE TABLE IF NOT EXISTS governed_state_head SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE governed_state_head TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE governed_state_head TYPE record<product>;
DEFINE FIELD IF NOT EXISTS state_kind ON TABLE governed_state_head TYPE string;
DEFINE FIELD IF NOT EXISTS state_id ON TABLE governed_state_head TYPE string;
DEFINE FIELD IF NOT EXISTS sequence ON TABLE governed_state_head TYPE int;
DEFINE FIELD IF NOT EXISTS revision_id ON TABLE governed_state_head TYPE string;
DEFINE FIELD IF NOT EXISTS commit_receipt_id ON TABLE governed_state_head TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE governed_state_head TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE governed_state_head TYPE datetime;
DEFINE INDEX IF NOT EXISTS governed_state_head_scope ON TABLE governed_state_head FIELDS product, state_kind, state_id UNIQUE;

DEFINE TABLE IF NOT EXISTS governed_state_commit_receipt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE governed_state_commit_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE governed_state_commit_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS state_kind ON TABLE governed_state_commit_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS state_id ON TABLE governed_state_commit_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS sequence ON TABLE governed_state_commit_receipt TYPE int;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE governed_state_commit_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON TABLE governed_state_commit_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS revision_id ON TABLE governed_state_commit_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS audit_id ON TABLE governed_state_commit_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE governed_state_commit_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE governed_state_commit_receipt TYPE datetime;
DEFINE INDEX IF NOT EXISTS governed_state_commit_stable ON TABLE governed_state_commit_receipt FIELDS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS governed_state_commit_revision ON TABLE governed_state_commit_receipt FIELDS product, revision_id UNIQUE;

DEFINE TABLE IF NOT EXISTS governed_state_audit SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE governed_state_audit TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE governed_state_audit TYPE record<product>;
DEFINE FIELD IF NOT EXISTS state_kind ON TABLE governed_state_audit TYPE string;
DEFINE FIELD IF NOT EXISTS state_id ON TABLE governed_state_audit TYPE string;
DEFINE FIELD IF NOT EXISTS sequence ON TABLE governed_state_audit TYPE int;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE governed_state_audit TYPE string;
DEFINE FIELD IF NOT EXISTS revision_id ON TABLE governed_state_audit TYPE string;
DEFINE FIELD IF NOT EXISTS commit_receipt_id ON TABLE governed_state_audit TYPE string;
DEFINE FIELD IF NOT EXISTS actor_ref ON TABLE governed_state_audit TYPE string;
DEFINE FIELD IF NOT EXISTS approval_receipt_ref ON TABLE governed_state_audit TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE governed_state_audit TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE governed_state_audit TYPE datetime;
DEFINE INDEX IF NOT EXISTS governed_state_audit_stable ON TABLE governed_state_audit FIELDS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS governed_state_audit_sequence ON TABLE governed_state_audit FIELDS product, state_kind, state_id, sequence UNIQUE;

