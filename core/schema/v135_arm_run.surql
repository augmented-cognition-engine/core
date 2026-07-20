-- schema/v135_arm_run.surql
-- The arm run ledger: a build becomes durable BEFORE it does any work, not after.
--
-- Until now the first durable trace of an arm build was the action_outcome row written
-- at the very end — a process killed mid-execute left nothing behind. arm_run is the
-- task ledger (written at dispatch) and arm_run_event is the append-only progress log
-- (one immutable row per completed phase). Mirrors reasoning_run / reasoning_event
-- (v117/v122) — same dual-ledger shape, same fail-safe contract.

DEFINE TABLE arm_run SCHEMALESS;
DEFINE FIELD product     ON arm_run TYPE record<product>;
DEFINE FIELD spec        ON arm_run TYPE option<record<agent_spec>>;
DEFINE FIELD intent      ON arm_run TYPE string;
DEFINE FIELD arm_domain  ON arm_run TYPE string;
-- running | verified | failed | parked
--   failed = the work was wrong (reversible; the workspace is discarded)
--   parked = we never found out (the environment broke; the workspace is PRESERVED
--            and a human is needed). Collapsing these two was the old lie.
DEFINE FIELD status      ON arm_run TYPE string DEFAULT 'running';
DEFINE FIELD reason      ON arm_run TYPE option<string>;
DEFINE FIELD diagnosis   ON arm_run TYPE option<string>;   -- parked only: what a human must fix
DEFINE FIELD attempts    ON arm_run TYPE int DEFAULT 0;    -- 1 + repair attempts spent
DEFINE FIELD trace_id    ON arm_run TYPE option<string>;
DEFINE FIELD started_at  ON arm_run TYPE datetime DEFAULT time::now();
DEFINE FIELD ended_at    ON arm_run TYPE option<datetime>;

-- The open-runs query (interrupted builds) reads status + started_at.
DEFINE INDEX idx_arm_run_product_status ON arm_run FIELDS product, status;
DEFINE INDEX idx_arm_run_product_ts     ON arm_run FIELDS product, started_at;

-- Append-only phase log. seq is caller-supplied and monotonic per run.
DEFINE TABLE arm_run_event SCHEMALESS;
DEFINE FIELD run        ON arm_run_event TYPE record<arm_run>;
DEFINE FIELD seq        ON arm_run_event TYPE int;
-- planned | executed | verified | failed | parked | repair_attempt | critic
DEFINE FIELD phase      ON arm_run_event TYPE string;
DEFINE FIELD payload    ON arm_run_event TYPE object DEFAULT {};
DEFINE FIELD created_at ON arm_run_event TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_arm_run_event_run_seq ON arm_run_event FIELDS run, seq;

-- action_outcome learns the same distinction. SCHEMALESS, so these are declarations of
-- intent for readers (the depth scorer / promotion path), not a migration of old rows:
-- pre-existing rows simply carry no parked flag, which reads as False.
DEFINE FIELD parked    ON action_outcome TYPE option<bool>;
DEFINE FIELD diagnosis ON action_outcome TYPE option<string>;
DEFINE FIELD attempts  ON action_outcome TYPE option<int>;    -- how many tries it took (learning signal)
DEFINE FIELD run       ON action_outcome TYPE option<record<arm_run>>;

UPSERT config_entry SET key = 'schema_version', value = '135' WHERE key = 'schema_version';
