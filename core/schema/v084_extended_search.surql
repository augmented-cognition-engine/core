-- v084: Extended FTS + HNSW on knowledge graph nodes
-- Enables ace_search to surface decisions and functions — not just insights.
-- Previously only insight had semantic search. Now the full knowledge layer is searchable.
--
-- Requires ace_text analyzer from v062.
-- Uses REMOVE ... IF EXISTS for idempotency (DEFINE INDEX doesn't overwrite in SurrealDB v3).
--
-- graph_decision : FTS on title + description; HNSW on embedding (768-dim)
-- graph_function : FTS on name + parameters;   HNSW on embedding (768-dim)
-- insight        : adds tags FTS for topical filtering (progressive disclosure item)

-- ── graph_decision ────────────────────────────────────────────────────────────
-- SurrealDB v3 FTS is single-field only — one index per field.
REMOVE INDEX IF EXISTS decision_title_search ON TABLE graph_decision;
DEFINE INDEX decision_title_search
    ON TABLE graph_decision
    FIELDS title
    FULLTEXT ANALYZER ace_text BM25(1.2, 0.75);

REMOVE INDEX IF EXISTS decision_desc_search ON TABLE graph_decision;
DEFINE INDEX decision_desc_search
    ON TABLE graph_decision
    FIELDS description
    FULLTEXT ANALYZER ace_text BM25(1.2, 0.75);

DEFINE FIELD embedding ON TABLE graph_decision TYPE option<array<float>>;
REMOVE INDEX IF EXISTS decision_hnsw ON TABLE graph_decision;
DEFINE INDEX decision_hnsw
    ON TABLE graph_decision
    FIELDS embedding
    HNSW DIMENSION 768 DIST COSINE EFC 150 M 12;

-- ── graph_function ────────────────────────────────────────────────────────────
REMOVE INDEX IF EXISTS fn_search ON TABLE graph_function;
DEFINE INDEX fn_search
    ON TABLE graph_function
    FIELDS name
    FULLTEXT ANALYZER ace_text BM25(1.2, 0.75);

DEFINE FIELD embedding ON TABLE graph_function TYPE option<array<float>>;
REMOVE INDEX IF EXISTS fn_hnsw ON TABLE graph_function;
DEFINE INDEX fn_hnsw
    ON TABLE graph_function
    FIELDS embedding
    HNSW DIMENSION 768 DIST COSINE EFC 150 M 12;

-- ── insight: tags FTS for topical filtering ───────────────────────────────────
-- Enables "show me insights tagged error_handling" without full content scan.
-- tags is array<string>; SurrealDB FTS on arrays indexes each element.
REMOVE INDEX IF EXISTS insight_tags_search ON TABLE insight;
DEFINE INDEX insight_tags_search
    ON TABLE insight
    FIELDS tags
    FULLTEXT ANALYZER ace_text BM25(1.2, 0.75);

-- ── Version ───────────────────────────────────────────────────────────────────
UPDATE config_entry SET value = 84 WHERE key = 'schema_version';
