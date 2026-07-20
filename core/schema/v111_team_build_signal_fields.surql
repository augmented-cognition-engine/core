-- schema/v111_team_build_signal_fields.surql

-- Adds team-build identifier fields to composition_signal (Phase B spec
-- docs/superpowers/specs/2026-05-25-ace-cost-aware-reasoning-phase-b-design.md).
--
-- All fields are option<...> — backward compatible. Phase B-onward
-- from_request_with_team writes one signal per lens with:
--   lens         = the discipline this row's reasoning ran for
--   lens_set     = the full lens roster for the build this row belongs to
--   recipe_slug  = the recipe that ran for this lens
--
-- Legacy MultiPhaseExecutor rows leave these fields NULL; queries that
-- analyze team-build patterns filter WHERE lens_set IS NOT NULL.

DEFINE FIELD lens        ON composition_signal TYPE option<string>;
DEFINE FIELD lens_set    ON composition_signal TYPE option<array<string>>;
DEFINE FIELD recipe_slug ON composition_signal TYPE option<string>;
