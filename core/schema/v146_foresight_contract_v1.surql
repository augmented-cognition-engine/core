-- F1: additive versioned forecast/resolution contracts and product-scoped calibration.
-- Historical decision_prediction, prediction_outcome, and archetype_calibration rows are not
-- rewritten or inferred. Read projections must surface them as legacy/partial.

DEFINE FIELD IF NOT EXISTS contract_version ON TABLE decision_prediction TYPE option<string>;
DEFINE FIELD IF NOT EXISTS forecast_contract ON TABLE decision_prediction TYPE option<object>;
DEFINE FIELD IF NOT EXISTS resolution_status ON TABLE decision_prediction TYPE option<string>;

DEFINE FIELD IF NOT EXISTS contract_version ON TABLE prediction_outcome TYPE option<string>;
DEFINE FIELD IF NOT EXISTS resolution_contract ON TABLE prediction_outcome TYPE option<object>;
DEFINE FIELD IF NOT EXISTS resolution_state ON TABLE prediction_outcome TYPE option<string>;
DEFINE FIELD IF NOT EXISTS score_eligible ON TABLE prediction_outcome TYPE option<bool>;
DEFINE FIELD IF NOT EXISTS non_score_reason ON TABLE prediction_outcome TYPE option<string>;
DEFINE FIELD IF NOT EXISTS intervention_status ON TABLE prediction_outcome TYPE option<string>;
DEFINE FIELD IF NOT EXISTS applicability_conditions_met ON TABLE prediction_outcome TYPE option<bool>;
DEFINE FIELD IF NOT EXISTS observation_refs ON TABLE prediction_outcome TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS confounders ON TABLE prediction_outcome TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS missing_evidence ON TABLE prediction_outcome TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS resolution_reason ON TABLE prediction_outcome TYPE option<string>;

DEFINE FIELD IF NOT EXISTS product ON TABLE archetype_calibration TYPE option<record<product>>;
DEFINE INDEX IF NOT EXISTS ac_product_archetype_discipline ON TABLE archetype_calibration
    FIELDS product, archetype, discipline;
DEFINE INDEX IF NOT EXISTS po_product_resolution ON TABLE prediction_outcome
    FIELDS product, resolution_state, closed_at;

UPDATE config_entry SET value = '146' WHERE key = 'schema_version';
