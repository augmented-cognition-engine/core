-- schema/v023_orchestration_events.surql
-- Runtime event persistence for the orchestration layer.
-- Enables debugging, replay, and orchestration intelligence.
-- Spec: docs/ace-25-execution-architecture.md §4

-- orchestration_run: one record per orchestrate()/stream() call
DEFINE TABLE orchestration_run SCHEMAFULL;
DEFINE FIELD org         ON TABLE orchestration_run TYPE record<org>;
DEFINE FIELD run_id      ON TABLE orchestration_run TYPE string;
DEFINE FIELD pattern     ON TABLE orchestration_run TYPE string;
DEFINE FIELD status      ON TABLE orchestration_run TYPE string;
DEFINE FIELD source      ON TABLE orchestration_run TYPE string DEFAULT 'direct';
DEFINE FIELD domain_path ON TABLE orchestration_run TYPE option<string>;
DEFINE FIELD agent_count ON TABLE orchestration_run TYPE int DEFAULT 1;
DEFINE FIELD duration_ms ON TABLE orchestration_run TYPE int DEFAULT 0;
DEFINE FIELD task_id     ON TABLE orchestration_run TYPE option<string>;
DEFINE FIELD error       ON TABLE orchestration_run TYPE option<string>;
DEFINE FIELD created_at  ON TABLE orchestration_run TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_or_org  ON TABLE orchestration_run FIELDS org, created_at;
DEFINE INDEX idx_or_run  ON TABLE orchestration_run FIELDS run_id UNIQUE;

-- orchestration_event: individual events within a run
DEFINE TABLE orchestration_event SCHEMAFULL;
DEFINE FIELD org         ON TABLE orchestration_event TYPE record<org>;
DEFINE FIELD run_id      ON TABLE orchestration_event TYPE string;
DEFINE FIELD event_type  ON TABLE orchestration_event TYPE string;
DEFINE FIELD payload     ON TABLE orchestration_event TYPE object DEFAULT {};
DEFINE FIELD created_at  ON TABLE orchestration_event TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_oe_run  ON TABLE orchestration_event FIELDS run_id, created_at;

-- Bump schema version
UPDATE config_entry SET value = '23' WHERE key = 'schema_version';
