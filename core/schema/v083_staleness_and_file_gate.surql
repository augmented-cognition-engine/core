-- v083: Staleness tracking + observation file-path indexing
-- Powers the File Read Gate (fast observation lookup by file) and
-- insight invalidation when source files change.
--
-- insight: adds stale_at, stale_reason, source_files
--   - stale_at       set when a graph_event or decision invalidates this insight
--   - stale_reason   why (file_modified | decision_superseded | manual)
--   - source_files   which file paths this insight references (populated by synthesizer)
--   - confirmed_count how many times a session re-confirmed this as accurate
--
-- observation: adds file-path + status composite index for sub-ms gate lookups

-- ── insight: staleness fields ─────────────────────────────────────────────────
DEFINE FIELD stale_at        ON TABLE insight TYPE option<datetime>;
DEFINE FIELD stale_reason    ON TABLE insight TYPE option<string>;
DEFINE FIELD source_files    ON TABLE insight TYPE array<string> DEFAULT [];
DEFINE FIELD confirmed_count ON TABLE insight TYPE int           DEFAULT 0;

DEFINE INDEX idx_ins_stale   ON TABLE insight FIELDS stale_at,     product;
DEFINE INDEX idx_ins_src     ON TABLE insight FIELDS source_files;
DEFINE INDEX idx_ins_conf    ON TABLE insight FIELDS confirmed_count, product;

-- ── observation: composite indexes for file-gate and queue draining ───────────
-- file_path is already written by the capture pipeline (SCHEMALESS field exists).
-- Adding typed definition + index so queries hit B-tree, not full scan.
DEFINE FIELD file_path ON TABLE observation TYPE option<string>;

REMOVE INDEX IF EXISTS idx_obs_file    ON TABLE observation;
REMOVE INDEX IF EXISTS idx_obs_queue   ON TABLE observation;
DEFINE INDEX idx_obs_file  ON TABLE observation FIELDS file_path, product;
DEFINE INDEX idx_obs_queue ON TABLE observation FIELDS status, product, created_at;

-- ── Version ───────────────────────────────────────────────────────────────────
UPDATE config_entry SET value = 83 WHERE key = 'schema_version';
