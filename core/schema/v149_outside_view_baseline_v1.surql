-- F1: grounded, product-scoped outside-view baselines from settled analogue outcomes.
-- Additive only: historical forecasts and resolutions remain unchanged. Read projections expose
-- older rows as lacking a frozen outside view rather than reconstructing one after the fact.

DEFINE FIELD IF NOT EXISTS outside_view_version ON TABLE decision_prediction TYPE option<string>;
DEFINE FIELD IF NOT EXISTS outside_view_baseline ON TABLE decision_prediction TYPE option<object>;

DEFINE FIELD IF NOT EXISTS outside_view_comparison ON TABLE prediction_outcome TYPE option<object>;

DEFINE INDEX IF NOT EXISTS po_product_score_eligible_closed ON TABLE prediction_outcome
    FIELDS product, score_eligible, closed_at;

UPDATE config_entry SET value = '149' WHERE key = 'schema_version';
