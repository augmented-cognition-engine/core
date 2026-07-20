-- schema/v113_insight_legacy_field_widen.surql

-- Fix a latent SCHEMAFULL data-integrity bug surfaced by the Phase 1 / A+
-- embedding backfill.
--
-- The insight table is SCHEMAFULL. Three fields were added by later migrations
-- as NON-optional types with DEFAULT clauses:
--   confirmed_count  TYPE int             DEFAULT 0
--   source_files     TYPE array<string>   DEFAULT []
--   org              TYPE record<...>
-- Rows created BEFORE those migrations never got the fields. SurrealDB does NOT
-- backfill DEFAULTs retroactively, so on ANY update it re-validates the whole
-- record, tries to coerce the absent field (NONE) to its non-option type, and
-- rejects the entire update with a per-statement ERR — silently, because the
-- client only raises on top-level errors. Result: ~15.6k legacy insights (≈68%
-- of the corpus) could not be updated by ANY process (decay, calibration,
-- supersession, embedding backfill).
--
-- Widening these to option<...> permits the absent/NONE state on legacy rows,
-- unblocking updates. This is backward compatible: option<T> still accepts every
-- existing T value; new writes keep defaulting via the DEFAULT clauses. The
-- types can be re-tightened later once the legacy rows are backfilled with
-- their defaults.

-- OVERWRITE is required: on this SurrealDB build a plain DEFINE FIELD on an
-- existing field errors with "already exists" (and the per-statement ERR is
-- swallowed by the migration runner), so the redefinition silently no-ops.
DEFINE FIELD OVERWRITE confirmed_count ON TABLE insight TYPE option<int>           DEFAULT 0;
DEFINE FIELD OVERWRITE source_files    ON TABLE insight TYPE option<array<string>> DEFAULT [];
DEFINE FIELD OVERWRITE org             ON TABLE insight TYPE option<record<product>>;
