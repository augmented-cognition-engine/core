-- schema/v120_routing_perf.surql

-- Durable escalation statistics for learned model-tier routing.
--
-- CascadeRouter tracks, per task_type, how often a cheap-tier attempt had to
-- escalate to a higher tier. Those counts lived only in-process (a short-lived
-- CLI run reset to zero every invocation, so the loop never reached the 5-sample
-- floor it needs). This table persists them per (product, task_type) so the
-- signal accumulates across restarts. route_model reads the aggregated rate from
-- an in-memory cache (seeded at startup via refresh_learned_routing) and
-- up-routes task types that chronically escalate. Mirrors the v118 tool_perf /
-- insight_model_affinity counter idiom (deterministic RecordID, atomic UPSERT).

DEFINE TABLE routing_perf SCHEMALESS;

DEFINE FIELD product    ON routing_perf TYPE record;
DEFINE FIELD task_type  ON routing_perf TYPE string;
DEFINE FIELD total      ON routing_perf TYPE int;
DEFINE FIELD escalated  ON routing_perf TYPE int;
DEFINE FIELD updated_at ON routing_perf TYPE datetime;

DEFINE INDEX idx_routing_perf_lookup ON routing_perf FIELDS product, task_type;
