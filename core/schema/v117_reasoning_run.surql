-- schema/v117_reasoning_run.surql

-- Persist every reasoning run as a dual-ledger:
--   Task Ledger     — thought, meta_skills, depth, discipline (written at start)
--   Progress Ledger — phases[] (cognitive_function/output/confidence) +
--                     trace[] (the executor's per-phase _last_trace metrics)
-- Fixes the "phase outputs are ephemeral, never written back" gap so
-- cross-session learning (instrument tuning, frontier-scan benchmarking,
-- loop-context) has durable source data.
--
-- SCHEMALESS because phases[]/trace[] are nested-object arrays (ACE convention:
-- SCHEMALESS for nested-object tables). The typed DEFINE FIELDs below are still
-- enforced by SurrealDB on write; SCHEMALESS only lets the nested phases[]/trace[]
-- objects through without per-key field definitions.

DEFINE TABLE reasoning_run SCHEMALESS;

DEFINE FIELD product     ON reasoning_run TYPE record;
DEFINE FIELD thought     ON reasoning_run TYPE string;
DEFINE FIELD meta_skills ON reasoning_run TYPE array;
DEFINE FIELD depth       ON reasoning_run TYPE int;
DEFINE FIELD discipline  ON reasoning_run TYPE option<string>;
DEFINE FIELD status      ON reasoning_run TYPE string;        -- running | complete
DEFINE FIELD conclusion  ON reasoning_run TYPE option<string>;
DEFINE FIELD phases      ON reasoning_run TYPE option<array>;
DEFINE FIELD trace       ON reasoning_run TYPE option<array>;
DEFINE FIELD started_at  ON reasoning_run TYPE datetime;
DEFINE FIELD ended_at    ON reasoning_run TYPE option<datetime>;

DEFINE INDEX idx_reasoning_run_product ON reasoning_run FIELDS product;
DEFINE INDEX idx_reasoning_run_recency ON reasoning_run FIELDS started_at;
