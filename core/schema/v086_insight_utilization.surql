-- Per-insight attribution history
DEFINE TABLE insight_utilization SCHEMALESS;
DEFINE FIELD insight     ON insight_utilization TYPE record<insight>;
DEFINE FIELD product     ON insight_utilization TYPE record<product>;
DEFINE FIELD loaded_count      ON insight_utilization TYPE int   DEFAULT 0;
DEFINE FIELD attributed_count  ON insight_utilization TYPE int   DEFAULT 0;
DEFINE FIELD utilization_score ON insight_utilization TYPE float DEFAULT 0.5;
DEFINE FIELD last_attributed   ON insight_utilization TYPE option<datetime>;
DEFINE FIELD updated_at        ON insight_utilization TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_iu_product_insight ON insight_utilization FIELDS product, insight UNIQUE;
DEFINE INDEX idx_iu_insight ON insight_utilization FIELDS insight;
UPDATE config_entry SET value = '86' WHERE key = 'schema_version';
