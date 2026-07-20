-- schema/v108_decision_capability_inference.surql

-- Backfill idempotency gate. Both forward-write (synthesizer) and the
-- backfill script/sentinel set this column the moment they touch a row.
DEFINE FIELD affected_capabilities_inferred_at ON decision TYPE option<datetime>;

-- LLM-inference confidence (review finding §2). NULL ⇒ human-authored.
DEFINE FIELD affected_capabilities_confidence  ON decision TYPE option<float>;

-- Capability-tier query is `WHERE product = $p AND affected_capabilities
-- CONTAINSANY $slugs ORDER BY created_at DESC LIMIT 5`. Without this index
-- the query degrades to a full-table scan. The 50ms latency target
-- (§10 Latency) is unachievable without it — review finding §3 made
-- this a correctness, not optimization, requirement.
DEFINE INDEX idx_decision_capability_recency ON decision
  FIELDS affected_capabilities, created_at;

-- Backfill filter relies on `affected_capabilities_inferred_at IS NONE`
-- across the full table. An index on the gate column avoids a sequential
-- scan as the table grows past ~50k rows.
DEFINE INDEX idx_decision_inferred_gate ON decision
  FIELDS affected_capabilities_inferred_at;

UPDATE config_entry SET value = '108' WHERE key = 'schema_version';
