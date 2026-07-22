-- F1: typed proper scoring for resolved forecast consequences.
-- Additive only. Historical outcomes retain their legacy calibration diagnostic and are not
-- retroactively assigned interval semantics or Prediction Score v1 records.

DEFINE FIELD IF NOT EXISTS prediction_score_version ON TABLE prediction_outcome TYPE option<string>;
DEFINE FIELD IF NOT EXISTS prediction_score ON TABLE prediction_outcome TYPE option<object>;

DEFINE INDEX IF NOT EXISTS po_product_prediction_score_closed ON TABLE prediction_outcome
    FIELDS product, prediction_score_version, closed_at;

UPDATE config_entry SET value = '150' WHERE key = 'schema_version';
