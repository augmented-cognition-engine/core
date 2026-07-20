-- v044: Fix object fields that silently reject nested data in SurrealDB v3
--
-- SCHEMAFULL tables with TYPE object reject unknown subfields. Adding
-- FLEXIBLE allows arbitrary nested keys while keeping the type constraint.
-- Tables also converted to SCHEMALESS per project convention.

-- briefing
DEFINE TABLE briefing SCHEMALESS;
REMOVE FIELD IF EXISTS metrics ON briefing;
DEFINE FIELD metrics ON briefing TYPE object FLEXIBLE;

-- engine_run
DEFINE TABLE engine_run SCHEMALESS;
REMOVE FIELD IF EXISTS results ON engine_run;
DEFINE FIELD results ON engine_run TYPE none | object FLEXIBLE;

-- chat_message
DEFINE TABLE chat_message SCHEMALESS;
REMOVE FIELD IF EXISTS classification ON chat_message;
DEFINE FIELD classification ON chat_message TYPE none | object FLEXIBLE;

-- task
DEFINE TABLE task SCHEMALESS;
REMOVE FIELD IF EXISTS engagement ON task;
DEFINE FIELD engagement ON task TYPE none | object FLEXIBLE;
REMOVE FIELD IF EXISTS intelligence_loaded ON task;
DEFINE FIELD intelligence_loaded ON task TYPE none | object FLEXIBLE;
REMOVE FIELD IF EXISTS intelligence_utilization ON task;
DEFINE FIELD intelligence_utilization ON task TYPE none | object FLEXIBLE;
REMOVE FIELD IF EXISTS ipm_vector ON task;
DEFINE FIELD ipm_vector ON task TYPE none | object FLEXIBLE;
REMOVE FIELD IF EXISTS token_usage ON task;
DEFINE FIELD token_usage ON task TYPE none | object FLEXIBLE;

-- idea
DEFINE TABLE idea SCHEMALESS;
REMOVE FIELD IF EXISTS brief ON idea;
DEFINE FIELD brief ON idea TYPE none | object FLEXIBLE;
REMOVE FIELD IF EXISTS classification ON idea;
DEFINE FIELD classification ON idea TYPE none | object FLEXIBLE;
REMOVE FIELD IF EXISTS effort_estimate ON idea;
DEFINE FIELD effort_estimate ON idea TYPE none | object FLEXIBLE;
REMOVE FIELD IF EXISTS research ON idea;
DEFINE FIELD research ON idea TYPE none | object FLEXIBLE;

-- capability
DEFINE TABLE capability SCHEMALESS;
REMOVE FIELD IF EXISTS intent ON capability;
DEFINE FIELD intent ON capability TYPE none | object FLEXIBLE;
REMOVE FIELD IF EXISTS reality ON capability;
DEFINE FIELD reality ON capability TYPE none | object FLEXIBLE;

-- calibration
DEFINE TABLE calibration SCHEMALESS;
REMOVE FIELD IF EXISTS data ON calibration;
DEFINE FIELD data ON calibration TYPE none | object FLEXIBLE;

-- calibration_snapshot
DEFINE TABLE calibration_snapshot SCHEMALESS;
REMOVE FIELD IF EXISTS buckets ON calibration_snapshot;
DEFINE FIELD buckets ON calibration_snapshot TYPE none | object FLEXIBLE;
