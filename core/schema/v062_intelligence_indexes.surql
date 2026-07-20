-- v062: Intelligence indexes + observation queue
-- Enables BM25 keyword search + HNSW vector similarity on insight table.
-- Adds status queue fields to observation for the worker service.
-- NOTE: SurrealDB v3 uses FULLTEXT (not SEARCH) for full-text indexes.
-- NOTE: Statements are single-line to avoid CLI multi-line parsing issues.
-- NOTE: REMOVE ... IF EXISTS used to make re-runnable (DEFINE does not overwrite).

-- ── Insight: full-text search ────────────────────────────────────────────────
DEFINE ANALYZER ace_text TOKENIZERS blank,class FILTERS ascii,lowercase,snowball(english);
REMOVE INDEX IF EXISTS insight_search ON insight;
DEFINE INDEX insight_search ON TABLE insight FIELDS content FULLTEXT ANALYZER ace_text BM25(1.2, 0.75);

-- ── Insight: vector similarity (768-dim = ONNX CodeRankEmbed default) ────────
DEFINE FIELD embedding ON TABLE insight TYPE option<array<float>>;
REMOVE INDEX IF EXISTS insight_hnsw ON insight;
DEFINE INDEX insight_hnsw ON TABLE insight FIELDS embedding HNSW DIMENSION 768 DIST COSINE EFC 150 M 12;

-- ── Observation: worker queue fields ─────────────────────────────────────────
DEFINE FIELD status ON TABLE observation TYPE string DEFAULT 'pending';
DEFINE FIELD processed_at ON TABLE observation TYPE option<datetime>;
DEFINE FIELD error ON TABLE observation TYPE option<string>;

-- Mark existing observations as pre-worker (not in the queue).
-- Only newly created observations start with status = 'pending'.
UPDATE observation SET status = 'pre-worker' WHERE status IS NONE OR status = '';

-- ── Version ──────────────────────────────────────────────────────────────────
UPDATE config_entry SET value = '62' WHERE key = 'schema_version';
