-- v057: cognitive composition layer
-- instrument_perf: tracks which frameworks perform best per cognitive function
-- meta_skill: stores the 22 meta-skill definitions seeded by engine/cognition/seed.py

DEFINE TABLE instrument_perf SCHEMALESS;

-- Fields written at runtime:
-- meta_skill: string (e.g. "coding_intelligence")
-- phase: int (0-5)
-- cognitive_function: string (frame|prioritize|choose|validate|allocate|critique)
-- framework_slug: string
-- task_type: string
-- discipline: string
-- outcome_score: float (0.0-1.0, backfilled by feedback)
-- org: record<org>
-- created_at: datetime

DEFINE INDEX idx_instrument_perf_lookup
  ON TABLE instrument_perf
  FIELDS org, meta_skill, cognitive_function, framework_slug;

DEFINE TABLE meta_skill SCHEMALESS;

-- Fields written by seed.py:
-- slug: string (e.g. "coding_intelligence")
-- name: string
-- description: string
-- domain_intelligences: array<string>
-- recipe: object (serialized MetaSkillRecipe)
-- created_at: datetime

DEFINE INDEX idx_meta_skill_slug
  ON TABLE meta_skill
  FIELDS slug UNIQUE;

UPSERT config_entry SET key = 'schema_version', value = '57'
    WHERE key = 'schema_version';
