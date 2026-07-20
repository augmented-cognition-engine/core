-- schema/v139_reeval_freshness_marked.surql
-- Decouple the freshness-drain from the re-evaluation queue's lifecycle.
--
-- Adversarial review (2026-07-15) caught a real collision: the */15 metabolism_drainer
-- was flipping every pending reeval_request to status='done', but rederive_pending AND
-- pending_reevaluations (the observability + the shadow re-derivation) both key on
-- status='pending'. So the drainer preempted them within 15 minutes and the whole seam
-- was inert in prod — hidden by an e2e test that never ran the drainer between enqueue
-- and rederive.
--
-- Fix: the freshness-mark is a crude INTERIM belief-side signal, not a resolution. Track
-- it with its own flag and leave the request OPEN (pending) until it is genuinely
-- resolved (re-derivation → apply per §5). Then the cron drain and the manual
-- re-derivation coexist on one queue without the drain destroying the other's state.
--
-- option<bool> (not plain bool): reeval_request is SCHEMAFULL, and a non-option field
-- with a default is not backfilled onto pre-v139 rows — v3 would then reject every UPDATE
-- on those rows (the v113 legacy-row trap). option<> lets legacy rows read NONE; the drain
-- filters `freshness_marked != true`, which matches both false and NONE.

DEFINE FIELD IF NOT EXISTS freshness_marked ON reeval_request TYPE option<bool> DEFAULT false;
DEFINE INDEX IF NOT EXISTS reeval_freshmark ON reeval_request FIELDS status, freshness_marked;

UPSERT config_entry SET key = 'schema_version', value = '139' WHERE key = 'schema_version';
