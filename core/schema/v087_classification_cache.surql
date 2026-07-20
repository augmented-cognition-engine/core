DEFINE TABLE classification_cache SCHEMALESS;
DEFINE FIELD product               ON classification_cache TYPE record<product>;
DEFINE FIELD description           ON classification_cache TYPE string;
DEFINE FIELD description_embedding ON classification_cache TYPE option<array<float>>;
DEFINE FIELD result                ON classification_cache TYPE object;
DEFINE FIELD hit_count             ON classification_cache TYPE int     DEFAULT 0;
DEFINE FIELD created_at            ON classification_cache TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_cc_product_created ON classification_cache FIELDS product, created_at;
UPDATE config_entry SET value = '87' WHERE key = 'schema_version';
