-- schema/v021_evolution.surql
-- Evolution engine tables: run tracking, source reputation, autonomy levels.
-- Spec: docs/superpowers/specs/2026-03-23-evolution-engine.md §9

-- === Evolution engine run details ===
DEFINE TABLE evolution_run SCHEMAFULL;
DEFINE FIELD org              ON evolution_run TYPE record<org>;
DEFINE FIELD phase            ON evolution_run TYPE string;
DEFINE FIELD hypotheses       ON evolution_run TYPE array;
DEFINE FIELD findings         ON evolution_run TYPE array;
DEFINE FIELD experiments_run  ON evolution_run TYPE int DEFAULT 0;
DEFINE FIELD committed        ON evolution_run TYPE int DEFAULT 0;
DEFINE FIELD proposed         ON evolution_run TYPE int DEFAULT 0;
DEFINE FIELD failed           ON evolution_run TYPE int DEFAULT 0;
DEFINE FIELD total_cost       ON evolution_run TYPE float DEFAULT 0.0;
DEFINE FIELD modification_manifest ON evolution_run TYPE option<object>;
DEFINE FIELD created_at       ON evolution_run TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_evo_run ON TABLE evolution_run FIELDS org, created_at;

-- === Source reputation tracking ===
DEFINE TABLE source_reputation SCHEMAFULL;
DEFINE FIELD org              ON source_reputation TYPE record<org>;
DEFINE FIELD url_domain       ON source_reputation TYPE string;
DEFINE FIELD source_type      ON source_reputation TYPE string;
DEFINE FIELD findings_count   ON source_reputation TYPE int DEFAULT 0;
DEFINE FIELD committed_count  ON source_reputation TYPE int DEFAULT 0;
DEFINE FIELD accuracy_rate    ON source_reputation TYPE float DEFAULT 0.5;
DEFINE FIELD domains_useful   ON source_reputation TYPE array DEFAULT [];
DEFINE FIELD last_used        ON source_reputation TYPE option<datetime>;
DEFINE FIELD created_at       ON source_reputation TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_source_rep ON TABLE source_reputation FIELDS org, url_domain UNIQUE;

-- === Autonomy level per domain ===
DEFINE TABLE autonomy_level SCHEMAFULL;
DEFINE FIELD org              ON autonomy_level TYPE record<org>;
DEFINE FIELD domain_path      ON autonomy_level TYPE string;
DEFINE FIELD level            ON autonomy_level TYPE string DEFAULT 'supervised';
DEFINE FIELD commits_total    ON autonomy_level TYPE int DEFAULT 0;
DEFINE FIELD commits_accurate ON autonomy_level TYPE int DEFAULT 0;
DEFINE FIELD accuracy_rate    ON autonomy_level TYPE float DEFAULT 0.0;
DEFINE FIELD last_promotion   ON autonomy_level TYPE option<datetime>;
DEFINE FIELD last_demotion    ON autonomy_level TYPE option<datetime>;
DEFINE FIELD created_at       ON autonomy_level TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_autonomy ON TABLE autonomy_level FIELDS org, domain_path UNIQUE;

-- === Schema version ===
UPDATE config_entry SET value = '21' WHERE key = 'schema_version';
