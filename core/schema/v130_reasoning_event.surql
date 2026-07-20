-- schema/v130_reasoning_event.surql
-- Append-only event log for reasoning runs (evolve run_ledger). reasoning_run (v117) keeps ONE
-- mutable row per run (snapshot); this adds immutable per-event rows (history) so runs are replayable
-- and there's a checkpoint substrate for forkable foresight / sleeptime consolidation. Append-only
-- BY CONVENTION: the writer (run_ledger.append_event) only CREATEs; nothing UPDATEs/DELETEs an event.
DEFINE TABLE reasoning_event SCHEMALESS;
DEFINE FIELD run        ON reasoning_event TYPE record<reasoning_run>;
DEFINE FIELD seq        ON reasoning_event TYPE int;        -- monotonic per run → ordered replay
DEFINE FIELD event_type ON reasoning_event TYPE string;     -- run_started | phase | run_complete | run_failed
DEFINE FIELD payload    ON reasoning_event TYPE option<object>;
DEFINE FIELD created_at ON reasoning_event TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_re_run_seq ON reasoning_event FIELDS run, seq;
