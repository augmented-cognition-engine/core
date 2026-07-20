-- v063: Final org cleanup — remove stale org field data and drop the org table.
--
-- v061 ran REMOVE FIELD + UPDATE ... UNSET org across all tables. Several tables
-- escaped cleanup because:
--   - SCHEMAFULL UNSET is ignored for fields removed from schema
--   - Rows with created_at:NONE fail schema re-validation on any UPDATE
--   - An index (idx_or_org) on orchestration_run blocked field removal
--
-- Tables with persistent stale org data after v061:
--   - initiative: 3 rows (e2e test artifacts) — deleted
--   - orchestration_event: 80 rows (org as raw string 'org:default', no created_at) — deleted
--   - engine_run: 14 rows (org as RecordID product:platform, no created_at) — cleaned via DEFINE+UNSET+REMOVE
--   - orchestration_run: 16 rows (org as raw string, no created_at, schema validation blocks UPDATE) — deleted
--
-- The org TABLE itself was never dropped by prior migrations.
--
-- This migration:
--   1. Drops the org table (removes all 3 legacy records + table definition)
--   2. Attempts UNSET on initiative (may be no-op due to SCHEMAFULL; handled live)
--   3. Deletes orchestration_event rows with product IS NONE (pre-migration garbage)

REMOVE TABLE org;

-- initiative: attempt UNSET (e2e test rows deleted live; this is belt-and-suspenders)
UPDATE initiative UNSET org WHERE org IS NOT NONE;

-- orchestration_event: delete pre-migration rows (no product, no created_at)
DELETE orchestration_event WHERE product IS NONE;

UPDATE config_entry SET value = '63' WHERE key = 'schema_version';
