-- v051: session_digest table for compressed session traces
-- Fed by session_compressor sentinel engine, consumed by briefing engine.
-- Spec: docs/superpowers/specs/2026-03-31-proactive-pm-pipeline-design.md §2

DEFINE TABLE session_digest SCHEMALESS;
DEFINE FIELD org ON session_digest TYPE record<org>;
DEFINE FIELD session_id ON session_digest TYPE string;
DEFINE FIELD period ON session_digest TYPE string;
DEFINE FIELD summary ON session_digest TYPE string;
DEFINE FIELD decisions ON session_digest TYPE array;
DEFINE FIELD blockers ON session_digest TYPE array;
DEFINE FIELD outcomes ON session_digest TYPE array;
DEFINE FIELD tasks_executed ON session_digest TYPE int;
DEFINE FIELD disciplines_touched ON session_digest TYPE array;
DEFINE FIELD intelligence_used ON session_digest TYPE array;
DEFINE FIELD quality_signals ON session_digest TYPE object;
DEFINE FIELD created_at ON session_digest TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_digest_org ON session_digest FIELDS org, period;

UPSERT config_entry SET value = 'v051' WHERE key = 'schema_version';
