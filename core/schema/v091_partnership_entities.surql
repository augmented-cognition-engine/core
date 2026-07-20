-- v091: partnership entities — promote UX primitives + thesis commitments to first-class graph data
--
-- Two tables:
--   partnership_pattern    — 15 rows, one per partnership interaction primitive
--   partnership_commitment — 5 rows, one per architectural partnership commitment
--
-- Existing required_pattern_relevance (v089) becomes the multi-pillar relevance graph for
-- partnership_pattern; its `pattern` field is a logical FK to partnership_pattern.slug
-- (enforced at the Python boundary; see scripts/seed_partnership_patterns.py).

DEFINE TABLE partnership_pattern SCHEMALESS;
DEFINE FIELD slug                ON partnership_pattern TYPE string;
DEFINE FIELD name                ON partnership_pattern TYPE string;
DEFINE FIELD family              ON partnership_pattern TYPE string;
DEFINE FIELD tier                ON partnership_pattern TYPE string;
DEFINE FIELD primary_pillar      ON partnership_pattern TYPE string;
DEFINE FIELD primary_discipline  ON partnership_pattern TYPE option<string>;
DEFINE FIELD prerequisite_ref    ON partnership_pattern TYPE option<string>;
DEFINE FIELD source_doc_ref      ON partnership_pattern TYPE string;
DEFINE FIELD status              ON partnership_pattern TYPE string DEFAULT "designed";
DEFINE FIELD created_at          ON partnership_pattern TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_pp_slug         ON partnership_pattern FIELDS slug UNIQUE;
DEFINE INDEX idx_pp_tier         ON partnership_pattern FIELDS tier;
DEFINE INDEX idx_pp_family       ON partnership_pattern FIELDS family;

DEFINE TABLE partnership_commitment SCHEMALESS;
DEFINE FIELD slug                ON partnership_commitment TYPE string;
DEFINE FIELD name                ON partnership_commitment TYPE string;
DEFINE FIELD summary             ON partnership_commitment TYPE string;
DEFINE FIELD primary_pillar      ON partnership_commitment TYPE string;
DEFINE FIELD secondary_pillars   ON partnership_commitment TYPE option<array<string>>;
DEFINE FIELD source_doc_ref      ON partnership_commitment TYPE string;
DEFINE FIELD created_at          ON partnership_commitment TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_pc_slug         ON partnership_commitment FIELDS slug UNIQUE;

-- ─── Version bump ─────────────────────────────────────────────────────────────

UPDATE config_entry SET value = '91' WHERE key = 'schema_version';
