-- schema/v122_run_event_seq.surql

-- Per-event monotonic sequence for the orchestration resume cursor. M2 made
-- task_id non-unique per event (token deltas share a perspective task_id), so the
-- old _replay cursor (walk to first row matching last_task_id) over-replays. seq is
-- a clean per-event boundary: _replay returns rows with seq > last_seq. SCHEMALESS
-- table; the typed field + index back the cursor query.
--
-- Migration note: pre-migration rows default to seq=0. _replay uses seq > $last_seq
-- and clients start at last_seq=0, so those seq=0 rows are EXCLUDED from replay (NOT
-- "sorted first" / replayed). Accepted tradeoff — pre-migration runs are treated as
-- expired; there is no backfill.

DEFINE FIELD seq ON run_event TYPE int DEFAULT 0;
DEFINE INDEX run_event_run_seq ON TABLE run_event COLUMNS run_id, seq;
