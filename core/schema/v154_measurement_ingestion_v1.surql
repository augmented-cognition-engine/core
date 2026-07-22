-- F1: fail-closed ingestion of explicit, plan-linked structured metric samples.
-- Raw samples are never resolution evidence themselves. A complete, internally consistent run
-- produces an ordinary Comparator Observation v1 through the existing evidence boundary.

DEFINE FIELD IF NOT EXISTS measurement_contract_version ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS measurement_contract ON TABLE observation TYPE option<object>;
DEFINE FIELD IF NOT EXISTS measurement_source_type ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS measurement_plan_id ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS measurement_run_id ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS measurement_slot ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS measurement_idempotency_key ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS measurement_ingestion_status ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS measurement_comparator_observation ON TABLE observation TYPE option<record<observation>>;
DEFINE FIELD IF NOT EXISTS measured_at ON TABLE observation TYPE option<datetime>;

DEFINE FIELD IF NOT EXISTS measurement_ingestion_version ON TABLE decision_prediction TYPE option<string>;
DEFINE FIELD IF NOT EXISTS measurement_ingestion_state ON TABLE decision_prediction TYPE option<object>;
DEFINE FIELD IF NOT EXISTS measurement_ingestion_status ON TABLE decision_prediction TYPE option<string>;
DEFINE FIELD IF NOT EXISTS measurement_ingestion_updated_at ON TABLE decision_prediction TYPE option<datetime>;

DEFINE INDEX IF NOT EXISTS observation_product_measurement_run ON TABLE observation
    FIELDS product, affected_prediction, measurement_plan_id, measurement_run_id, measurement_slot;
DEFINE INDEX IF NOT EXISTS observation_product_measurement_request ON TABLE observation
    FIELDS product, measurement_idempotency_key;

UPDATE config_entry SET value = '154' WHERE key = 'schema_version';
