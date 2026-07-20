-- schema/v109_decision_recency_index.surql

-- Layer 5's recency-tier loader does:
--   SELECT ... FROM decision WHERE product = <record>$p [shared filters]
--   ORDER BY created_at DESC LIMIT $lim
--
-- Without an index on created_at, SurrealDB scans the full decision table.
-- At the current dev-DB size (~14k rows) this pushes past the 50ms recency-
-- tier deadline (observed 52.5ms loader-total against product:platform during
-- post-implementation E2E verification — recency tier timed out, the other
-- two tiers landed under deadline). The discipline + capability tier indexes
-- shipped in v108 are fine; recency was the gap.
--
-- decision:lv6stu70piemfwypde2e — Layer 5 perf fix.
DEFINE INDEX idx_decision_recency ON decision FIELDS created_at;

UPDATE config_entry SET value = '109' WHERE key = 'schema_version';
