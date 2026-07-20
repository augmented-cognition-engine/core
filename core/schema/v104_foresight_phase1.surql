-- schema/v104_foresight_phase1.surql
-- Foresight Phase 1: prediction, outcome, and archetype calibration tables.

DEFINE TABLE decision_prediction SCHEMALESS;
-- Fields written by engine/foresight/forecaster.py:
--   decision:               record<decision>        — the decision this predicts
--   product:                record<product>
--   archetype:              string                  — which archetype made the decision
--   discipline:             string                  — domain context
--   horizon_days:           int                     — when to check back (7–30)
--   expected_changes:       array<object>           — [{capability_id, score_delta, confidence}]
--   primary_risk:           string                  — one falsifiable sentence
--   leading_indicators:     array<string>
--   falsification_condition: string
--   closed:                 bool                    — false until reconciler processes it
--   created_at:             datetime

DEFINE TABLE prediction_outcome SCHEMALESS;
-- Fields written by engine/foresight/reconciler.py after closing a prediction:
--   prediction:             record<decision_prediction>
--   decision:               record<decision>
--   product:                record<product>
--   archetype:              string
--   discipline:             string
--   calibration_score:      float   — 0.0–1.0; 1.0 = perfect prediction
--   predicted_deltas:       object  — {capability_id: predicted_delta}
--   actual_deltas:          object  — {capability_id: actual_delta}
--   closed_at:              datetime

DEFINE TABLE archetype_calibration SCHEMALESS;
-- Fields maintained by engine/foresight/reconciler.py (upsert on each close):
--   archetype:              string
--   discipline:             string
--   calibration_score:      float   — running weighted average (EMA, alpha=0.3)
--   sample_count:           int
--   updated_at:             datetime

-- Indexes for common query patterns.
DEFINE INDEX dp_product_closed ON TABLE decision_prediction COLUMNS product, closed;
DEFINE INDEX dp_decision ON TABLE decision_prediction COLUMNS decision;
DEFINE INDEX po_archetype_discipline ON TABLE prediction_outcome COLUMNS archetype, discipline;
DEFINE INDEX ac_archetype_discipline ON TABLE archetype_calibration COLUMNS archetype, discipline;

UPDATE config_entry SET value = '104' WHERE key = 'schema_version';
