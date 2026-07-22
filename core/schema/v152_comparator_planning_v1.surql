-- F1: optional comparator planning frozen at forecast creation.
-- Plans are advisory, require operator confirmation, and are never observation evidence or
-- resolution-eligible merely because they exist.

DEFINE FIELD IF NOT EXISTS comparator_plan_version ON TABLE decision_prediction TYPE option<string>;
DEFINE FIELD IF NOT EXISTS comparator_plan ON TABLE decision_prediction TYPE option<object>;
DEFINE FIELD IF NOT EXISTS comparator_plan_status ON TABLE decision_prediction TYPE option<string>;

DEFINE INDEX IF NOT EXISTS dp_product_comparator_plan_created ON TABLE decision_prediction
    FIELDS product, comparator_plan_status, created_at;

UPDATE config_entry SET value = '152' WHERE key = 'schema_version';
