-- schema/v129_afferent_edges.surql
-- Close the octopus loop: when a build's action_outcome is recorded, edge it back into the graph so
-- the loop is traversable. outcome_addresses->agent_spec (spec build history), outcome_exercises->
-- capability (the dynamic reality signal the capability audit reads — stronger than a static glob),
-- outcome_touches->graph_file (the build's footprint). SCHEMALESS: edges carry light, evolving
-- metadata (passed). Mirrors the realizes / cross_project_dep RELATION pattern.
--
-- Names are namespaced with outcome_ because the plain verbs addresses/touches are ALREADY relation
-- tables from v037 (four_layer_live: addresses->capability_quality, agent_session->touches->
-- capability) with incompatible field types — a RELATE into them is coerced away (silent edge loss),
-- caught by a live smoke test. The three names below are genuinely new (grep-verified: no prior
-- DEFINE TABLE for any of them, nor for the stem `exercises`).
--
-- NOTE: there is no v128 in committed history. A v128 that reused the plain colliding names was
-- authored, applied to one dev DB, found to collide, and withdrawn before commit. This migration is
-- ONLY the three new tables — it deliberately does NOT re-DEFINE the v037 tables (a plain re-DEFINE
-- of an existing table/field errors "already exists" on SurrealDB v3 — see v058/v113 — which would
-- abort the run; and the withdrawn v128's only lasting effect on that one dev DB was repaired there).
DEFINE TABLE outcome_addresses TYPE RELATION SCHEMALESS;
DEFINE TABLE outcome_exercises TYPE RELATION SCHEMALESS;
DEFINE TABLE outcome_touches   TYPE RELATION SCHEMALESS;
