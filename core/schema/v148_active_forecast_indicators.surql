-- F1: additive active leading-indicator evidence and operational aggregate state.
-- The immutable forecast contract is not rewritten. Indicator evaluations remain separate
-- observation rows; only the replaceable operational aggregate on decision_prediction changes.

DEFINE FIELD IF NOT EXISTS indicator_contract_version ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS indicator_contract ON TABLE observation TYPE option<object>;
DEFINE FIELD IF NOT EXISTS indicator_local_id ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS indicator_effect ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS indicator_idempotency_key ON TABLE observation TYPE option<string>;

DEFINE FIELD IF NOT EXISTS indicator_state_version ON TABLE decision_prediction TYPE option<string>;
DEFINE FIELD IF NOT EXISTS indicator_evidence_state ON TABLE decision_prediction TYPE option<object>;
DEFINE FIELD IF NOT EXISTS indicator_status ON TABLE decision_prediction TYPE option<string>;
DEFINE FIELD IF NOT EXISTS indicator_updated_at ON TABLE decision_prediction TYPE option<datetime>;

DEFINE INDEX IF NOT EXISTS idx_observation_product_prediction_indicator ON TABLE observation
    FIELDS product, affected_prediction, indicator_local_id, observed_at;
DEFINE INDEX IF NOT EXISTS idx_observation_product_indicator_request ON TABLE observation
    FIELDS product, indicator_idempotency_key;

UPDATE config_entry SET value = '148' WHERE key = 'schema_version';
