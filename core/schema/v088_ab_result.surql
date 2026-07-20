-- schema/v088_ab_result.surql
-- A/B shadow baseline results — each row is one shadow comparison.
-- judge_preference: "treatment" (intel-augmented won), "control", or "tie".
-- SCHEMALESS: allows future fields without migration.

DEFINE TABLE ab_result SCHEMALESS;

DEFINE FIELD product           ON ab_result TYPE record<product>;
DEFINE FIELD task_id           ON ab_result TYPE option<record<task>>;
DEFINE FIELD discipline        ON ab_result TYPE string DEFAULT "";
DEFINE FIELD depth             ON ab_result TYPE int DEFAULT 2;
DEFINE FIELD judge_preference  ON ab_result TYPE string;
DEFINE FIELD judge_rationale   ON ab_result TYPE string DEFAULT "";
DEFINE FIELD created_at        ON ab_result TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_abr_product_created ON ab_result FIELDS product, created_at;

-- ─── Version bump ─────────────────────────────────────────────────────────────

UPDATE config_entry SET value = '88' WHERE key = 'schema_version';
