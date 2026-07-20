-- v141: Remove the dead org field from agent_feedback.
--
-- Second instance of the v140 class, found by the 2026-07-15 schema drift
-- audit (fresh replay vs live). v032 defined agent_feedback.org as a REQUIRED
-- record<org>. The v058/v059/v061 org→product retirement removed org from
-- every other table but never touched agent_feedback, so replaying these
-- files from scratch leaves the field required — while the org table itself
-- no longer exists at end of replay, and feedback_handler.py writes product,
-- never org. Every CREATE agent_feedback on a fresh install therefore fails
-- field validation, silently (per-statement ERR string; the v113 scar).
--
-- Long-lived internal databases are immune: their agent_feedback.org
-- definition was already dropped outside these files (live shows no
-- definition — the same hand-patch drift v140 documents for observation).
REMOVE FIELD IF EXISTS org ON TABLE agent_feedback;
UPDATE agent_feedback UNSET org;

UPSERT config_entry SET key = 'schema_version', value = '141' WHERE key = 'schema_version';
