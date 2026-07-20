-- v080: strategic_score table — stores per-run 5-dimension strategic scores
-- produced by StrategicPrioritizer for trend analysis and history.
-- SCHEMALESS: dimensions dict varies as new dimensions are added.

DEFINE TABLE strategic_score SCHEMALESS
  PERMISSIONS NONE;

-- Index for querying latest score per capability+dimension combo
DEFINE INDEX ss_lookup ON strategic_score FIELDS product, capability_slug, dimension UNIQUE;

-- Time-based index for trend queries
DEFINE INDEX ss_time ON strategic_score FIELDS product, scored_at;
