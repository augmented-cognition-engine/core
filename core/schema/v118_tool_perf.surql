-- schema/v118_tool_perf.surql

-- Learned per-context tool affinity, mirroring instrument_perf for frameworks.
-- Backs ToolClassifier: which tool helped which cognitive step, scoped by
-- (product, cognitive_function, meta_skill, task_type, discipline). Empty until
-- outcome-writing lands (deferred); ToolClassifier cold-starts to static fallback.

DEFINE TABLE tool_perf SCHEMALESS;

DEFINE FIELD product            ON tool_perf TYPE record;
DEFINE FIELD cognitive_function ON tool_perf TYPE string;
DEFINE FIELD meta_skill         ON tool_perf TYPE string;
DEFINE FIELD task_type          ON tool_perf TYPE string;
DEFINE FIELD discipline         ON tool_perf TYPE string;
DEFINE FIELD tool_slug          ON tool_perf TYPE string;
DEFINE FIELD outcome_score      ON tool_perf TYPE float;
DEFINE FIELD created_at         ON tool_perf TYPE datetime;

DEFINE INDEX idx_tool_perf_lookup ON tool_perf FIELDS product, cognitive_function;
