-- schema/v137_reeval_request.surql
-- The grounding metabolism's durable re-evaluation queue.
--
-- When a grounded canvas object changes, the beliefs grounded in it (grounds_of)
-- can no longer be assumed current, so they are enqueued here; a drain pass marks
-- them freshness-stale. Durable + inspectable (the arm_run / action_outcome ethos):
-- you can ask "what is pending re-evaluation, and which ground changed to cause it?"
--
-- IF NOT EXISTS everywhere: version-skip is the primary idempotency, but this also
-- makes the file safe to re-apply (v3's plain re-DEFINE errors "already exists").
--
-- Spec: docs/superpowers/specs/2026-07-15-grounding-metabolism-design.md

DEFINE TABLE IF NOT EXISTS reeval_request SCHEMAFULL;

-- belief: the grounded reasoning node to re-evaluate. Untyped `record` for the same
-- reason grounds.in is — reasoning kinds live across ~10 tables.
DEFINE FIELD IF NOT EXISTS belief         ON reeval_request TYPE record;
-- trigger_object: the canvas object whose change caused this request (provenance).
DEFINE FIELD IF NOT EXISTS trigger_object ON reeval_request TYPE record;
DEFINE FIELD IF NOT EXISTS reason         ON reeval_request TYPE string DEFAULT 'ground_changed';
DEFINE FIELD IF NOT EXISTS status         ON reeval_request TYPE string DEFAULT 'pending'
  ASSERT $value IN ['pending', 'done'];
DEFINE FIELD IF NOT EXISTS created_at     ON reeval_request TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS drained_at     ON reeval_request TYPE option<datetime>;

-- Pending-lookup index: enqueue's idempotency check and drain both hit
-- (belief, trigger_object, status) / (status); index so neither scans.
DEFINE INDEX IF NOT EXISTS reeval_pending ON reeval_request FIELDS belief, trigger_object, status;
DEFINE INDEX IF NOT EXISTS reeval_status  ON reeval_request FIELDS status;

UPSERT config_entry SET key = 'schema_version', value = '137' WHERE key = 'schema_version';
