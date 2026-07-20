-- v003: maturation tracking tables
-- Reference: docs/ace-18-complete-schema.md §4 (Operational)

-- ================================================================
-- MATURATION — cached maturation scores per node
-- ================================================================
DEFINE TABLE maturation SCHEMAFULL;
DEFINE FIELD org              ON TABLE maturation TYPE record<org>;
DEFINE FIELD node_type        ON TABLE maturation TYPE string;
    -- specialty | subdomain | domain | org
DEFINE FIELD node_id          ON TABLE maturation TYPE record;
DEFINE FIELD phase            ON TABLE maturation TYPE int;
    -- 1=nascent, 2=forming, 3=reliable, 4=expert, 5=authoritative
DEFINE FIELD phase_name       ON TABLE maturation TYPE string;
DEFINE FIELD score            ON TABLE maturation TYPE int;
    -- 0-100
DEFINE FIELD coverage_ratio   ON TABLE maturation TYPE option<float>;
DEFINE FIELD metrics          ON TABLE maturation TYPE object;
DEFINE FIELD calculated_at    ON TABLE maturation TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_mat_node     ON TABLE maturation FIELDS org, node_type, node_id;

-- ================================================================
-- MATURATION_HISTORY — track phase changes over time
-- ================================================================
DEFINE TABLE maturation_history SCHEMAFULL;
DEFINE FIELD org              ON TABLE maturation_history TYPE record<org>;
DEFINE FIELD node_type        ON TABLE maturation_history TYPE string;
DEFINE FIELD node_id          ON TABLE maturation_history TYPE record;
DEFINE FIELD phase            ON TABLE maturation_history TYPE int;
DEFINE FIELD score            ON TABLE maturation_history TYPE int;
DEFINE FIELD recorded_at      ON TABLE maturation_history TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_mat_hist     ON TABLE maturation_history FIELDS org, node_id, recorded_at;

UPSERT config_entry SET key = 'schema_version', value = '3'
    WHERE key = 'schema_version';
