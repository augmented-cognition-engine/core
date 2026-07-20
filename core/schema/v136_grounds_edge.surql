-- schema/v136_grounds_edge.surql
-- The `grounds` edge — ACE's node<->canvas join (the substrate's node/canvas grounding).
--
-- The substrate contract makes the reasoning graph the mind and the canvas its
-- projection. `grounds` is the bidirectional join that lets a reasoning node know
-- WHICH canvas thing it is about, so that (a) when the object changes the engine
-- knows which beliefs to re-evaluate, and (b) when the human circles an object the
-- interpreter knows which subgraph they point into.
--
-- Modeled as a RELATE edge, not a field array, BECAUSE of the reverse direction:
-- the metabolism's hot path is "given this changed object, which beliefs ground in
-- it?" — which a field-array answers only by scanning every node, but a graph edge
-- answers natively via canvas_object <-grounds<- nodes. See
-- docs/superpowers/specs/2026-07-14-grounds-edge-design.md.
--
-- IF NOT EXISTS everywhere: primary idempotency is schema_apply's version-skip
-- (v136 runs once), but this also makes the file safe to re-apply directly — v3's
-- plain DEFINE errors "already exists" on a second run (see v113/v129).
--
-- The data backfill of decision.cited_artifact_ids into `grounds` runs separately
-- via `scripts/backfill_grounds.py` (idempotent, reuses the tested ground()); a
-- pure-SurrealQL RELATE loop over string ids is neither idempotent nor
-- record-coercion-safe. The field is kept, deprecated -> derive from the edge.

-- ── the edge ────────────────────────────────────────────────────────────────
DEFINE TABLE IF NOT EXISTS grounds TYPE RELATION SCHEMAFULL;

-- in: ANY reasoning node. Untyped `record` because reasoning kinds live in ~10
-- tables (insight, decision, conflict, product_question, graph_insight, ...) and
-- the projector discriminates kind at the membrane, not here.
DEFINE FIELD IF NOT EXISTS in  ON grounds TYPE record;

-- out: a canvas target. Today only canvas_artifact (v103) exists; discourse marks
-- and sheets get their tables with the canvas build and this widens to a union
-- then. Kept as `record` so it can widen without a rewrite.
DEFINE FIELD IF NOT EXISTS out ON grounds TYPE record;

-- plane: which canvas plane the target lives on. 'artifact' is the only populated
-- value until scratch/discourse/sheet tables exist; the enum is declared in full
-- now so the projector's routing is stable.
DEFINE FIELD IF NOT EXISTS plane ON grounds TYPE string
  ASSERT $value IN ['artifact', 'scratch', 'discourse', 'sheet']
  DEFAULT 'artifact';

-- role: HOW the node relates to the target. 'about' (artifact/scratch) ·
-- 'originates' (discourse: the node came from this mark) · 'motivates' (sheet:
-- the node motivates this proposal).
DEFINE FIELD IF NOT EXISTS role ON grounds TYPE string
  ASSERT $value IN ['about', 'originates', 'motivates']
  DEFAULT 'about';

-- primary: one grounding per node may be marked primary (the caption anchor /
-- where a ripple originates). At most one true per `in` — enforced in the write
-- path (ground()), not the schema.
DEFINE FIELD IF NOT EXISTS primary ON grounds TYPE bool DEFAULT false;

DEFINE FIELD IF NOT EXISTS created_at ON grounds TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS source ON grounds TYPE string DEFAULT 'engine'
  ASSERT $value IN ['human-gesture', 'engine', 'migration'];

-- Reverse-lookup index: the metabolism's hot path is "what grounds in this
-- object?" — index `out` so canvas_object <-grounds<- nodes is a lookup, not a scan.
DEFINE INDEX IF NOT EXISTS grounds_out ON grounds FIELDS out;
DEFINE INDEX IF NOT EXISTS grounds_in  ON grounds FIELDS in;

-- ── bundled silent-drop fix (found in the audit) ─────────────────────────────
-- freshness.py writes freshness_score / freshness_last_computed / governed_files
-- / contradiction_count onto the SCHEMAFULL insight table (and the DEFINE-FIELD'd
-- decision table), but none were declared in any .surql — so every write was
-- silently dropped and the scorer's output never persisted.
--
-- option<> is REQUIRED, not stylistic: a NON-option field on a SCHEMAFULL table
-- with legacy rows makes v3 reject EVERY update on those rows (it re-coerces the
-- absent field NONE -> non-option and errors per-statement). That is exactly the
-- ~15.6k-legacy-row breakage v113 was written to repair; option<> avoids repeating it.
DEFINE FIELD IF NOT EXISTS freshness_score         ON TABLE insight  TYPE option<float>;
DEFINE FIELD IF NOT EXISTS freshness_last_computed ON TABLE insight  TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS governed_files          ON TABLE insight  TYPE option<array<string>> DEFAULT [];
DEFINE FIELD IF NOT EXISTS contradiction_count     ON TABLE insight  TYPE option<int> DEFAULT 0;
DEFINE FIELD IF NOT EXISTS freshness_score         ON TABLE decision TYPE option<float>;
DEFINE FIELD IF NOT EXISTS freshness_last_computed ON TABLE decision TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS governed_files          ON TABLE decision TYPE option<array<string>> DEFAULT [];
DEFINE FIELD IF NOT EXISTS contradiction_count     ON TABLE decision TYPE option<int> DEFAULT 0;

UPSERT config_entry SET key = 'schema_version', value = '136' WHERE key = 'schema_version';
