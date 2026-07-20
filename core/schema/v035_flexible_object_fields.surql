-- v035: Allow arbitrary sub-fields in object-typed columns (SurrealDB v3 SCHEMAFULL compat)
-- SCHEMAFULL tables reject nested writes to object fields unless sub-fields are defined.

-- engine_run.results stores engine-specific data (insights_decayed, conflicts_found, etc.)
DEFINE FIELD results.* ON TABLE engine_run TYPE any;

-- briefing.metrics stores aggregated metrics from engines
DEFINE FIELD metrics.* ON TABLE briefing TYPE any;

-- task has several object fields that store arbitrary nested data
DEFINE FIELD intelligence_loaded.* ON task TYPE any;
DEFINE FIELD engagement.* ON task TYPE any;
DEFINE FIELD self_assessment.* ON task TYPE any;
DEFINE FIELD intelligence_utilization.* ON task TYPE any;
DEFINE FIELD calibrated_assessment.* ON task TYPE any;

-- task.self_assessment is used as float by engine code (failure_analysis, etc.)
-- v034 changed it to object, but engines query `self_assessment < 0.4`
REMOVE FIELD IF EXISTS self_assessment ON task;
DEFINE FIELD self_assessment ON task TYPE any;

-- task.user and task.workspace are required by original schema but engine-created tasks
-- (overnight engines, batch processes) don't always have a user/workspace context
REMOVE FIELD IF EXISTS user ON task;
DEFINE FIELD user ON task TYPE option<record<user>>;
REMOVE FIELD IF EXISTS workspace ON task;
DEFINE FIELD workspace ON task TYPE option<record<workspace>>;

-- conflict table needs detected_by field for conflict_detector engine provenance
DEFINE FIELD IF NOT EXISTS detected_by ON conflict TYPE option<string>;

UPSERT config_entry SET key = 'schema_version', value = '35'
    WHERE key = 'schema_version';
