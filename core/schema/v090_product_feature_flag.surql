-- v090: per-product feature flags (added for phase_aware_ranking_enabled gate)

DEFINE TABLE product_feature_flag SCHEMALESS;
DEFINE FIELD product   ON product_feature_flag TYPE record<product>;
DEFINE FIELD flag      ON product_feature_flag TYPE string;
DEFINE FIELD enabled     ON product_feature_flag TYPE bool;
DEFINE FIELD set_at    ON product_feature_flag TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_pff_lookup ON product_feature_flag FIELDS product, flag;

-- ─── Version bump ─────────────────────────────────────────────────────────────

UPDATE config_entry SET value = '90' WHERE key = 'schema_version';
