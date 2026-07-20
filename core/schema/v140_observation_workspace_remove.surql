-- v140: Remove the dead workspace field from observation.
--
-- v002 defined observation.workspace as option<record<workspace>>. v034 rebuilt
-- the table for the SCHEMALESS conversion and redefined workspace as a REQUIRED
-- record<workspace> — no option<>, no DEFAULT. v061 retired the workspace
-- concept ("early concept, never used") and removed the field from initiative
-- and recurring_initiative, but missed observation.
--
-- Consequence: on any database built by replaying these files in order (every
-- fresh install, including the open kernel export), EVERY `CREATE observation`
-- fails field validation — invisibly, because SurrealDB returns the
-- per-statement failure as an error string rather than raising (the same
-- failure class v113 documents for insight), parse_rows() maps error strings
-- to [], and POST /observe reported {"status": "queued"} regardless.
-- Long-lived internal databases never hit this: their live definition was
-- hand-patched outside these files. This migration converges both worlds.
--
-- workspace is dead per v061 — remove it outright, same pattern v061 used.
REMOVE FIELD IF EXISTS workspace ON TABLE observation;
UPDATE observation UNSET workspace;

UPSERT config_entry SET key = 'schema_version', value = '140' WHERE key = 'schema_version';
