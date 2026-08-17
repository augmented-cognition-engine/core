-- Slice 7: delegated headless governed-cognition review and activation.
--
-- Two append-only product-scoped receipt tables. The activation receipt is
-- written in the same transaction that asserts every governed-state head
-- precondition (both grants, SERVICE principal lifecycle, capability state)
-- and moves the cognition revision, head, and activation event.

DEFINE TABLE IF NOT EXISTS cognition_delegated_approval_receipt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_delegated_approval_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE cognition_delegated_approval_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE cognition_delegated_approval_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS request_ref ON TABLE cognition_delegated_approval_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS request_digest ON TABLE cognition_delegated_approval_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS replay_key ON TABLE cognition_delegated_approval_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON TABLE cognition_delegated_approval_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_hash ON TABLE cognition_delegated_approval_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS service_principal_ref ON TABLE cognition_delegated_approval_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_delegated_approval_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE cognition_delegated_approval_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS resolved_at ON TABLE cognition_delegated_approval_receipt TYPE datetime;
DEFINE INDEX IF NOT EXISTS cognition_delegated_approval_stable
  ON TABLE cognition_delegated_approval_receipt FIELDS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS cognition_delegated_approval_replay
  ON TABLE cognition_delegated_approval_receipt FIELDS product, replay_key UNIQUE;

DEFINE TABLE IF NOT EXISTS cognition_delegated_activation_receipt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE cognition_delegated_activation_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS request_ref ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS request_digest ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS approval_receipt_ref ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS replay_key ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_id ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS proposal_hash ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS service_principal_ref ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS result_revision_id ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS result_head_id ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS result_head_generation ON TABLE cognition_delegated_activation_receipt TYPE int;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_delegated_activation_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE cognition_delegated_activation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS activated_at ON TABLE cognition_delegated_activation_receipt TYPE datetime;
DEFINE INDEX IF NOT EXISTS cognition_delegated_activation_stable
  ON TABLE cognition_delegated_activation_receipt FIELDS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS cognition_delegated_activation_replay
  ON TABLE cognition_delegated_activation_receipt FIELDS product, replay_key UNIQUE;
