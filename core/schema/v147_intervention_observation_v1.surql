-- F1: additive, product-scoped Intervention Observation v1 persistence.
-- Forecasts remain immutable. Intervention observations are separate provenance-bearing rows;
-- historical generic observations are not rewritten or reinterpreted.

DEFINE FIELD IF NOT EXISTS affected_prediction ON TABLE observation TYPE option<record<decision_prediction>>;
DEFINE FIELD IF NOT EXISTS intervention_contract_version ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS intervention_contract ON TABLE observation TYPE option<object>;
DEFINE FIELD IF NOT EXISTS intervention_status ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS intervention_idempotency_key ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS applicability_conditions_met ON TABLE observation TYPE option<bool>;
DEFINE FIELD IF NOT EXISTS intervention_exposure ON TABLE observation TYPE option<float>;
DEFINE FIELD IF NOT EXISTS observed_at ON TABLE observation TYPE option<datetime>;

DEFINE INDEX IF NOT EXISTS idx_observation_product_prediction_observed ON TABLE observation
    FIELDS product, affected_prediction, observed_at;
DEFINE INDEX IF NOT EXISTS idx_observation_product_intervention_request ON TABLE observation
    FIELDS product, intervention_idempotency_key;

UPDATE config_entry SET value = '147' WHERE key = 'schema_version';
