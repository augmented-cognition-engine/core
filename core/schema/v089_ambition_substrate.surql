-- schema/v089_ambition_substrate.surql
-- Ambition substrate + phase-aware ranking infrastructure.
-- Spec: docs/superpowers/specs/2026-04-28-ambition-substrate-and-phase-aware-ranking-design.md v1.2.

-- ─── Ambition entity (Target + Phase per product) ──────────────────────────────

DEFINE TABLE ambition SCHEMALESS;
DEFINE FIELD product            ON ambition TYPE record<product>;
DEFINE FIELD target_json        ON ambition TYPE object DEFAULT {};
DEFINE FIELD phase_json         ON ambition TYPE object DEFAULT {};
DEFINE FIELD last_ingested_at   ON ambition TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_ambition_product ON ambition FIELDS product UNIQUE;

-- ─── Phase floor curves (pillar/discipline/sub-dim level) ──────────────────────

DEFINE TABLE phase_floors SCHEMALESS;
DEFINE FIELD pillar         ON phase_floors TYPE string;
DEFINE FIELD discipline     ON phase_floors TYPE option<string>;
DEFINE FIELD sub_dim        ON phase_floors TYPE option<string>;
DEFINE FIELD phase          ON phase_floors TYPE string;
DEFINE FIELD product_type   ON phase_floors TYPE string DEFAULT "default";
DEFINE FIELD scale          ON phase_floors TYPE string DEFAULT "application";
DEFINE FIELD floor_value    ON phase_floors TYPE float;
DEFINE FIELD source         ON phase_floors TYPE string DEFAULT "seed";
DEFINE FIELD set_by         ON phase_floors TYPE string DEFAULT "system";
DEFINE FIELD set_at         ON phase_floors TYPE datetime DEFAULT time::now();
DEFINE FIELD reason         ON phase_floors TYPE string DEFAULT "default seed";
DEFINE INDEX idx_phase_floors_lookup ON phase_floors
    FIELDS pillar, discipline, sub_dim, phase, product_type, scale UNIQUE;

-- ─── Required-pattern relevance (pattern → pillar.discipline) ──────────────────

DEFINE TABLE required_pattern_relevance SCHEMALESS;
DEFINE FIELD pattern        ON required_pattern_relevance TYPE string;
DEFINE FIELD pillar         ON required_pattern_relevance TYPE string;
DEFINE FIELD discipline     ON required_pattern_relevance TYPE option<string>;
DEFINE FIELD contribution   ON required_pattern_relevance TYPE float DEFAULT 0.5;
DEFINE INDEX idx_rpr_pattern ON required_pattern_relevance FIELDS pattern;

-- ─── Pillar score cache ────────────────────────────────────────────────────────

DEFINE TABLE pillar_score_cache SCHEMALESS;
DEFINE FIELD product            ON pillar_score_cache TYPE record<product>;
DEFINE FIELD pillar             ON pillar_score_cache TYPE string;
DEFINE FIELD score              ON pillar_score_cache TYPE float;
DEFINE FIELD computed_at        ON pillar_score_cache TYPE datetime DEFAULT time::now();
DEFINE FIELD invalidated_at     ON pillar_score_cache TYPE option<datetime>;
DEFINE INDEX idx_psc_lookup ON pillar_score_cache FIELDS product, pillar;

-- ─── Uncertainty queries (ask-when-uncertain syscall record) ───────────────────

DEFINE TABLE uncertainty_queries SCHEMALESS;
DEFINE FIELD product            ON uncertainty_queries TYPE record<product>;
DEFINE FIELD scope              ON uncertainty_queries TYPE string;
DEFINE FIELD question           ON uncertainty_queries TYPE string;
DEFINE FIELD fallback_action    ON uncertainty_queries TYPE string;
DEFINE FIELD posed_at           ON uncertainty_queries TYPE datetime DEFAULT time::now();
DEFINE FIELD answered_at        ON uncertainty_queries TYPE option<datetime>;
DEFINE FIELD answer             ON uncertainty_queries TYPE option<string>;
DEFINE FIELD status             ON uncertainty_queries TYPE string DEFAULT "open";
DEFINE INDEX idx_uq_product_status ON uncertainty_queries FIELDS product, status;

-- ─── Recommendation decay state ────────────────────────────────────────────────

DEFINE TABLE recommendation_decay_state SCHEMALESS;
DEFINE FIELD rec_id                          ON recommendation_decay_state TYPE string;
DEFINE FIELD product                         ON recommendation_decay_state TYPE record<product>;
DEFINE FIELD consecutive_briefings_at_top    ON recommendation_decay_state TYPE int DEFAULT 0;
DEFINE FIELD last_acknowledged_at            ON recommendation_decay_state TYPE option<datetime>;
DEFINE FIELD last_status_change_at           ON recommendation_decay_state TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_rds_rec ON recommendation_decay_state FIELDS rec_id UNIQUE;

-- ─── Product table: add product_type and product_scale fields ──────────────────

DEFINE FIELD product_type   ON product TYPE string DEFAULT "ai_native";
DEFINE FIELD product_scale  ON product TYPE string DEFAULT "application";

-- ─── Recommendation cache: add ranking-math columns ────────────────────────────

DEFINE FIELD pillar                       ON recommendation_cache TYPE option<string>;
DEFINE FIELD discipline                   ON recommendation_cache TYPE option<string>;
DEFINE FIELD floor                        ON recommendation_cache TYPE option<float>;
DEFINE FIELD gap                          ON recommendation_cache TYPE option<float>;
DEFINE FIELD ambition_relevance           ON recommendation_cache TYPE option<float>;
DEFINE FIELD consecutive_briefings_at_top ON recommendation_cache TYPE option<int>;

-- ─── Version bump ─────────────────────────────────────────────────────────────

UPDATE config_entry SET value = '89' WHERE key = 'schema_version';
