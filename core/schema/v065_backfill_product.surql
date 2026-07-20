-- v065: Backfill product = product:platform on rows that pre-date the org→product
-- rename wave (v058–v061). These rows were written before product was a required
-- field on memory and engine_run, so they have product IS NONE.
--
-- Counts at migration time:
--   memory     : 5,628 rows with product IS NONE
--   engine_run : 133   rows with product IS NONE
--
-- All belong to the single-tenant platform product.

UPDATE memory     SET product = product:platform WHERE product IS NONE;
UPDATE engine_run SET product = product:platform WHERE product IS NONE;

-- ─── Version bump ─────────────────────────────────────────────────────────────

UPDATE config_entry SET value = '65' WHERE key = 'schema_version';
