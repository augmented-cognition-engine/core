-- v007: scheduler + signals — engine execution log, output versioning, research queue
-- Reference: docs/ace-18-complete-schema.md lines 776-800
-- Spec: docs/superpowers/specs/2026-03-21-phase3a-scheduler-signals.md

-- ============================================================
-- ENGINE_RUN — overnight engine execution history
-- ============================================================
DEFINE TABLE engine_run SCHEMAFULL;
DEFINE FIELD org              ON TABLE engine_run TYPE record<org>;
DEFINE FIELD engine           ON TABLE engine_run TYPE string;
    -- decay_manager | conflict_detector | failure_analysis | gap_researcher |
    -- knowledge_verifier | specialty_deepener | world_monitor | briefing_generator
DEFINE FIELD domain           ON TABLE engine_run TYPE option<record<domain>>;
DEFINE FIELD status           ON TABLE engine_run TYPE string;
    -- running | completed | failed
DEFINE FIELD started_at       ON TABLE engine_run TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at     ON TABLE engine_run TYPE option<datetime>;
DEFINE FIELD duration_ms      ON TABLE engine_run TYPE option<int>;
DEFINE FIELD results          ON TABLE engine_run TYPE option<object>;
    -- engine-specific result data (insights_decayed, conflicts_found, etc.)
DEFINE FIELD results.*        ON TABLE engine_run TYPE any;
    -- allow arbitrary nested fields in results object
DEFINE FIELD cost             ON TABLE engine_run TYPE float DEFAULT 0.0;
DEFINE FIELD error            ON TABLE engine_run TYPE option<string>;
DEFINE INDEX idx_engrun       ON TABLE engine_run FIELDS org, engine, started_at;

-- ============================================================
-- OUTPUT_VERSION — revision tracking when users edit task outputs
-- ============================================================
DEFINE TABLE output_version SCHEMAFULL;
DEFINE FIELD org              ON TABLE output_version TYPE record<org>;
DEFINE FIELD task             ON TABLE output_version TYPE record<task>;
DEFINE FIELD version          ON TABLE output_version TYPE int;
DEFINE FIELD content          ON TABLE output_version TYPE string;
DEFINE FIELD change_reason    ON TABLE output_version TYPE option<string>;
    -- stores the diff summary or edit description
DEFINE FIELD requested_by     ON TABLE output_version TYPE option<record<user>>;
DEFINE FIELD created_at       ON TABLE output_version TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_outver       ON TABLE output_version FIELDS task, version;

-- ============================================================
-- RESEARCH_QUEUE — queued research for overnight engines
-- (Applied now so conflict_detector can queue research for Phase 3b)
-- ============================================================
DEFINE TABLE research_queue SCHEMAFULL;
DEFINE FIELD org              ON TABLE research_queue TYPE record<org>;
DEFINE FIELD query            ON TABLE research_queue TYPE string;
DEFINE FIELD context          ON TABLE research_queue TYPE string;
DEFINE FIELD priority         ON TABLE research_queue TYPE string DEFAULT 'medium';
    -- low | medium | high | critical
DEFINE FIELD source           ON TABLE research_queue TYPE string;
    -- failure-analysis | gap-detection | specialty-deepener | user-request | conflict-detector
DEFINE FIELD related_task     ON TABLE research_queue TYPE option<record<task>>;
DEFINE FIELD status           ON TABLE research_queue TYPE string DEFAULT 'pending';
    -- pending | in_progress | completed | failed
DEFINE FIELD created_at       ON TABLE research_queue TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at     ON TABLE research_queue TYPE option<datetime>;
DEFINE INDEX idx_rq_status    ON TABLE research_queue FIELDS org, status, priority;

-- ============================================================
-- Field additions to existing task table
-- ============================================================
DEFINE FIELD intelligence_utilization ON TABLE task TYPE option<object>;
    -- { loaded_count, reflected_count, ignored_count, reflected_ids, ignored_ids, utilization_rate }

UPSERT config_entry SET key = 'schema_version', value = '7'
    WHERE key = 'schema_version';
