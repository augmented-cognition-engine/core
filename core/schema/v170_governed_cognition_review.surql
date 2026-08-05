-- E1-C: immutable sourced proposals and human review receipts. Approval and
-- cognition_head movement are written in one transaction by the service.

DEFINE TABLE IF NOT EXISTS cognition_proposal SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE cognition_proposal TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE cognition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_hash ON TABLE cognition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS target_cognition_id ON TABLE cognition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS scope ON TABLE cognition_proposal TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS base_revision_id ON TABLE cognition_proposal TYPE option<string>;
DEFINE FIELD IF NOT EXISTS state ON TABLE cognition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_proposal TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE cognition_proposal TYPE datetime;
DEFINE INDEX IF NOT EXISTS cognition_proposal_stable ON TABLE cognition_proposal FIELDS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS cognition_proposal_product_state ON TABLE cognition_proposal FIELDS product, state, created_at;

DEFINE TABLE IF NOT EXISTS cognition_review_receipt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_review_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE cognition_review_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE cognition_review_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON TABLE cognition_review_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_hash ON TABLE cognition_review_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS actor_id ON TABLE cognition_review_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS actor_class ON TABLE cognition_review_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS disposition ON TABLE cognition_review_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS result_revision_id ON TABLE cognition_review_receipt TYPE option<string>;
DEFINE FIELD IF NOT EXISTS result_head_id ON TABLE cognition_review_receipt TYPE option<string>;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_review_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS reviewed_at ON TABLE cognition_review_receipt TYPE datetime;
DEFINE INDEX IF NOT EXISTS cognition_review_stable ON TABLE cognition_review_receipt FIELDS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS cognition_review_product_proposal ON TABLE cognition_review_receipt FIELDS product, proposal_id, reviewed_at;
