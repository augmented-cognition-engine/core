-- v066: benchmark_result table — stores ACE vs baseline graded comparisons.
--
-- Each row is one benchmark run: same task, same model, same rubric —
-- graded by an isolated GraderAgent subprocess. Tracks quality delta,
-- token consumption, cost, and ROI across disciplines over time.
--
-- SCHEMALESS: criteria_results is a nested array of objects (criterion + status + reasoning).
-- All scalar fields are explicitly defined for index efficiency.

DEFINE TABLE benchmark_result SCHEMALESS;

DEFINE FIELD product          ON benchmark_result TYPE record<product>;
DEFINE FIELD discipline       ON benchmark_result TYPE string DEFAULT '';
DEFINE FIELD model            ON benchmark_result TYPE string DEFAULT '';
DEFINE FIELD task             ON benchmark_result TYPE string;
DEFINE FIELD rubric           ON benchmark_result TYPE array<string>;

-- baseline (no ACE intelligence)
DEFINE FIELD baseline_met     ON benchmark_result TYPE int     DEFAULT 0;
DEFINE FIELD baseline_score   ON benchmark_result TYPE float   DEFAULT 0.0;
DEFINE FIELD baseline_tokens  ON benchmark_result TYPE int     DEFAULT 0;
DEFINE FIELD baseline_cost    ON benchmark_result TYPE float   DEFAULT 0.0;
DEFINE FIELD baseline_dur     ON benchmark_result TYPE float   DEFAULT 0.0;

-- ace (full intelligence stack)
DEFINE FIELD ace_met          ON benchmark_result TYPE int     DEFAULT 0;
DEFINE FIELD ace_score        ON benchmark_result TYPE float   DEFAULT 0.0;
DEFINE FIELD ace_tokens       ON benchmark_result TYPE int     DEFAULT 0;
DEFINE FIELD ace_cost         ON benchmark_result TYPE float   DEFAULT 0.0;
DEFINE FIELD ace_dur          ON benchmark_result TYPE float   DEFAULT 0.0;

-- deltas and ROI
DEFINE FIELD delta_criteria   ON benchmark_result TYPE int     DEFAULT 0;
DEFINE FIELD delta_score      ON benchmark_result TYPE float   DEFAULT 0.0;
DEFINE FIELD delta_tokens     ON benchmark_result TYPE int     DEFAULT 0;
DEFINE FIELD delta_cost       ON benchmark_result TYPE float   DEFAULT 0.0;
DEFINE FIELD roi              ON benchmark_result TYPE float   DEFAULT 0.0;

DEFINE FIELD verdict          ON benchmark_result TYPE string  DEFAULT 'tied';
DEFINE FIELD total_duration_s ON benchmark_result TYPE float   DEFAULT 0.0;
DEFINE FIELD created_at       ON benchmark_result TYPE datetime DEFAULT time::now();

-- Indexes for trend queries
DEFINE INDEX idx_br_product    ON benchmark_result FIELDS product, created_at;
DEFINE INDEX idx_br_discipline ON benchmark_result FIELDS product, discipline, created_at;
DEFINE INDEX idx_br_verdict    ON benchmark_result FIELDS product, verdict, created_at;

-- ─── Version bump ─────────────────────────────────────────────────────────────

UPDATE config_entry SET value = '66' WHERE key = 'schema_version';
