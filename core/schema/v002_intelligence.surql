-- v002: intelligence pipeline tables
-- Reference: docs/ace-18-complete-schema.md §2 (Intelligence) + §3 (Execution)

-- ================================================================
-- MEMORY — raw ingestion buffer (Level 1)
-- All sources write here. Observer promotes ~20-30% to observation.
-- ================================================================
DEFINE TABLE memory SCHEMAFULL;
DEFINE FIELD org              ON TABLE memory TYPE record<org>;
DEFINE FIELD workspace        ON TABLE memory TYPE option<record<workspace>>;
DEFINE FIELD session_id       ON TABLE memory TYPE option<string>;
DEFINE FIELD content          ON TABLE memory TYPE string;
DEFINE FIELD memory_type      ON TABLE memory TYPE string;
    -- chunk | document_fragment | feedback_signal | user_input | system_event
DEFINE FIELD source           ON TABLE memory TYPE string;
    -- capture_pipeline | document_ingestion | feedback | user_note | integration
DEFINE FIELD source_ref       ON TABLE memory TYPE option<string>;
DEFINE FIELD metadata         ON TABLE memory TYPE option<object>;
DEFINE FIELD processed        ON TABLE memory TYPE bool DEFAULT false;
DEFINE FIELD created_at       ON TABLE memory TYPE datetime DEFAULT time::now();
DEFINE FIELD expires_at       ON TABLE memory TYPE option<datetime>;
DEFINE INDEX idx_mem_unproc   ON TABLE memory FIELDS org, processed, created_at;
DEFINE INDEX idx_mem_session  ON TABLE memory FIELDS org, session_id, created_at;
DEFINE INDEX idx_mem_expire   ON TABLE memory FIELDS expires_at;

-- ================================================================
-- OBSERVATION — classified signals (Level 2)
-- Observer promotes ~20-30% of memories to observations
-- ================================================================
DEFINE TABLE observation SCHEMAFULL;
DEFINE FIELD org              ON TABLE observation TYPE record<org>;
DEFINE FIELD workspace        ON TABLE observation TYPE option<record<workspace>>;
DEFINE FIELD content          ON TABLE observation TYPE string;
DEFINE FIELD observation_type ON TABLE observation TYPE string;
    -- decision | correction | discovery | pattern | preference | failure | fact
DEFINE FIELD confidence       ON TABLE observation TYPE float;
DEFINE FIELD domain_hint      ON TABLE observation TYPE option<string>;
DEFINE FIELD source_memory    ON TABLE observation TYPE option<record<memory>>;
DEFINE FIELD source_memories  ON TABLE observation TYPE option<array<record<memory>>>;
DEFINE FIELD session_id       ON TABLE observation TYPE option<string>;
DEFINE FIELD synthesized      ON TABLE observation TYPE bool DEFAULT false;
DEFINE FIELD created_at       ON TABLE observation TYPE datetime DEFAULT time::now();
DEFINE FIELD expires_at       ON TABLE observation TYPE option<datetime>;
DEFINE INDEX idx_obs_unsynth  ON TABLE observation FIELDS org, synthesized, created_at;
DEFINE INDEX idx_obs_type     ON TABLE observation FIELDS org, observation_type, created_at;
DEFINE INDEX idx_obs_domain   ON TABLE observation FIELDS org, domain_hint;

-- ================================================================
-- INSIGHT — durable intelligence (Level 3)
-- Permanent: decays, gets contradicted, but never deleted
-- ================================================================
DEFINE TABLE insight SCHEMAFULL;
DEFINE FIELD org              ON TABLE insight TYPE record<org>;
DEFINE FIELD workspace        ON TABLE insight TYPE option<record<workspace>>;
DEFINE FIELD content          ON TABLE insight TYPE string;
DEFINE FIELD insight_type     ON TABLE insight TYPE string;
    -- fact | pattern | decision | correction | preference | convention | discovery
DEFINE FIELD tier             ON TABLE insight TYPE string;
    -- specialty | subdomain | domain | org | network
DEFINE FIELD domain           ON TABLE insight TYPE option<record<domain>>;
DEFINE FIELD subdomain        ON TABLE insight TYPE option<record<subdomain>>;
DEFINE FIELD specialty        ON TABLE insight TYPE option<record<specialty>>;
DEFINE FIELD clearance        ON TABLE insight TYPE string DEFAULT 'open';
DEFINE FIELD confidence       ON TABLE insight TYPE float;
DEFINE FIELD source_domain    ON TABLE insight TYPE string;
DEFINE FIELD source_observations ON TABLE insight TYPE option<array<record<observation>>>;
DEFINE FIELD derivation_chain ON TABLE insight TYPE option<array<record<insight>>>;
DEFINE FIELD tags             ON TABLE insight TYPE array<string> DEFAULT [];
DEFINE FIELD status           ON TABLE insight TYPE string DEFAULT 'active';
    -- active | contradicted | expired | archived
DEFINE FIELD contradicted_by  ON TABLE insight TYPE option<record<insight>>;
DEFINE FIELD last_confirmed   ON TABLE insight TYPE datetime DEFAULT time::now();
DEFINE FIELD decay_rate       ON TABLE insight TYPE float DEFAULT 0.01;
DEFINE FIELD ttl              ON TABLE insight TYPE option<duration>;
DEFINE FIELD created_at       ON TABLE insight TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at       ON TABLE insight TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_ins_domain   ON TABLE insight FIELDS org, domain, subdomain, specialty, status;
DEFINE INDEX idx_ins_tier     ON TABLE insight FIELDS org, tier, status;
DEFINE INDEX idx_ins_type     ON TABLE insight FIELDS org, insight_type, status;
DEFINE INDEX idx_ins_conf     ON TABLE insight FIELDS org, confidence, status;
DEFINE INDEX idx_ins_source   ON TABLE insight FIELDS org, source_domain, created_at;
DEFINE INDEX idx_ins_tags     ON TABLE insight FIELDS org, tags, status;

-- ================================================================
-- TASK — execution records
-- ================================================================
DEFINE TABLE task SCHEMAFULL;
DEFINE FIELD org              ON TABLE task TYPE record<org>;
DEFINE FIELD workspace        ON TABLE task TYPE record<workspace>;
DEFINE FIELD user             ON TABLE task TYPE record<user>;
DEFINE FIELD description      ON TABLE task TYPE string;
DEFINE FIELD domain_path      ON TABLE task TYPE string;
DEFINE FIELD archetype        ON TABLE task TYPE string DEFAULT 'executor';
DEFINE FIELD mode             ON TABLE task TYPE string DEFAULT 'reactive';
DEFINE FIELD intelligence_loaded ON TABLE task TYPE option<object>;
DEFINE FIELD output           ON TABLE task TYPE option<string>;
DEFINE FIELD self_assessment  ON TABLE task TYPE option<float>;
DEFINE FIELD feedback_human   ON TABLE task TYPE option<string>;
DEFINE FIELD feedback_score   ON TABLE task TYPE option<float>;
DEFINE FIELD cost             ON TABLE task TYPE float DEFAULT 0.0;
DEFINE FIELD model_used       ON TABLE task TYPE option<string>;
DEFINE FIELD session_id       ON TABLE task TYPE option<string>;
DEFINE FIELD status           ON TABLE task TYPE string DEFAULT 'pending';
    -- pending | running | completed | failed | cancelled
DEFINE FIELD created_at       ON TABLE task TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at     ON TABLE task TYPE option<datetime>;
DEFINE INDEX idx_task_org     ON TABLE task FIELDS org, workspace, status, created_at;
DEFINE INDEX idx_task_domain  ON TABLE task FIELDS org, domain_path, created_at;

-- ================================================================
-- CONFLICT — contradictions between insights
-- ================================================================
DEFINE TABLE conflict SCHEMAFULL;
DEFINE FIELD org              ON TABLE conflict TYPE record<org>;
DEFINE FIELD insight_a        ON TABLE conflict TYPE record<insight>;
DEFINE FIELD insight_b        ON TABLE conflict TYPE option<record<insight>>;
DEFINE FIELD conflicting_content ON TABLE conflict TYPE option<string>;
DEFINE FIELD explanation      ON TABLE conflict TYPE string;
DEFINE FIELD status           ON TABLE conflict TYPE string DEFAULT 'pending';
    -- pending | resolved | dismissed
DEFINE FIELD resolution       ON TABLE conflict TYPE option<string>;
DEFINE FIELD resolved_by      ON TABLE conflict TYPE option<record<user>>;
DEFINE FIELD resolved_at      ON TABLE conflict TYPE option<datetime>;
DEFINE FIELD created_at       ON TABLE conflict TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_conflict_org ON TABLE conflict FIELDS org, status;

-- Update specialty table to match doc 18 (adds fields missing from v001)
DEFINE FIELD description      ON TABLE specialty TYPE option<string>;
DEFINE FIELD maturation_phase ON TABLE specialty TYPE int DEFAULT 1;
DEFINE FIELD maturation_score ON TABLE specialty TYPE int DEFAULT 0;
DEFINE FIELD health_score     ON TABLE specialty TYPE float DEFAULT 0.0;

UPSERT config_entry SET key = 'schema_version', value = '2'
    WHERE key = 'schema_version';
