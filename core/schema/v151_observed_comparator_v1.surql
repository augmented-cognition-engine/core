-- F1: optional observed-comparator evidence for decision forecasts.
-- Comparator rows remain separate from the immutable forecast and can supply transparent
-- difference-in-differences effects to horizon-gated resolution when explicitly eligible.

DEFINE FIELD IF NOT EXISTS comparator_contract_version ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS comparator_contract ON TABLE observation TYPE option<object>;
DEFINE FIELD IF NOT EXISTS comparator_type ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS comparator_design ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS comparator_resolution_eligible ON TABLE observation TYPE option<bool>;
DEFINE FIELD IF NOT EXISTS comparator_idempotency_key ON TABLE observation TYPE option<string>;

DEFINE FIELD IF NOT EXISTS comparator_state_version ON TABLE decision_prediction TYPE option<string>;
DEFINE FIELD IF NOT EXISTS comparator_evidence_state ON TABLE decision_prediction TYPE option<object>;
DEFINE FIELD IF NOT EXISTS comparator_status ON TABLE decision_prediction TYPE option<string>;
DEFINE FIELD IF NOT EXISTS comparator_updated_at ON TABLE decision_prediction TYPE option<datetime>;

DEFINE FIELD IF NOT EXISTS comparator_context ON TABLE prediction_outcome TYPE option<object>;

DEFINE INDEX IF NOT EXISTS idx_observation_product_prediction_comparator ON TABLE observation
    FIELDS product, affected_prediction, comparator_resolution_eligible, observed_at;
DEFINE INDEX IF NOT EXISTS idx_observation_product_comparator_request ON TABLE observation
    FIELDS product, comparator_idempotency_key;

UPDATE config_entry SET value = '151' WHERE key = 'schema_version';
