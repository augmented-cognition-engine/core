-- v097: Seed-history support — indexes + capability_quality.seed_origin field
--
-- Context:
--   - decision.product is already defined (v054 added, v061 made required, v072 indexed
--     by (product, discipline_hint, outcome)). This adds an index on (product, created_at)
--     for efficient time-ordered scans by the seed script and downstream readers.
--   - briefing.product exists (v054) but the original briefing index (idx_brief_org from
--     v008) referenced the now-removed `org` field. This migration replaces it.
--   - capability_quality is SCHEMAFULL (v032). We need an explicit field declaration
--     to allow the seed script to mark synthetic rows.

-- (1) Decision: efficient (product, time) scans for time-windowed reads.
DEFINE INDEX idx_decision_product_created ON decision FIELDS product, created_at;

-- (2) Briefing: replace orphaned idx_brief_org (referenced removed 'org' field).
REMOVE INDEX idx_brief_org ON briefing;
DEFINE INDEX idx_brief_product_created ON briefing FIELDS product, created_at;

-- (3) capability_quality: schemaful, so seed_origin must be declared explicitly.
DEFINE FIELD seed_origin ON capability_quality TYPE option<string>;

UPDATE config_entry SET value = '97' WHERE key = 'schema_version';
