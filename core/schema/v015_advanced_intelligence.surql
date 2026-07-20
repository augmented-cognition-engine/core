-- v015: Advanced Intelligence — ROI tracking, calibration, experiment logging
-- Reference: docs/superpowers/specs/2026-03-22-phase7a-measurement-foundation.md

-- ============================================================
-- EXPERIMENT_LOG — stores experiment results for intelligence quality
-- ============================================================
DEFINE TABLE experiment_log SCHEMAFULL;
DEFINE FIELD org                 ON TABLE experiment_log TYPE record<org>;
DEFINE FIELD domain              ON TABLE experiment_log TYPE string;
DEFINE FIELD experiment_type     ON TABLE experiment_log TYPE string;
    -- intelligence_variant | routing_config | adversarial | framework_effectiveness
DEFINE FIELD control_description ON TABLE experiment_log TYPE string;
DEFINE FIELD variant_description ON TABLE experiment_log TYPE string;
DEFINE FIELD synthetic_task_count ON TABLE experiment_log TYPE int DEFAULT 0;
DEFINE FIELD control_mean        ON TABLE experiment_log TYPE float DEFAULT 0.0;
DEFINE FIELD variant_mean        ON TABLE experiment_log TYPE float DEFAULT 0.0;
DEFINE FIELD improvement         ON TABLE experiment_log TYPE float DEFAULT 0.0;
DEFINE FIELD p_value             ON TABLE experiment_log TYPE float DEFAULT 1.0;
DEFINE FIELD significant         ON TABLE experiment_log TYPE bool DEFAULT false;
DEFINE FIELD committed           ON TABLE experiment_log TYPE bool DEFAULT false;
DEFINE FIELD details             ON TABLE experiment_log TYPE option<object>;
DEFINE FIELD created_at          ON TABLE experiment_log TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_exp_domain      ON TABLE experiment_log FIELDS org, domain;
DEFINE INDEX idx_exp_type        ON TABLE experiment_log FIELDS org, experiment_type;

-- ============================================================
-- CALIBRATION — per-org calibration curves
-- ============================================================
DEFINE TABLE calibration SCHEMAFULL;
DEFINE FIELD org                 ON TABLE calibration TYPE record<org>;
DEFINE FIELD data                ON TABLE calibration TYPE object;
    -- {domain: {bucket_0.1: {predicted, actual, count, miscalibration}, ...}}
DEFINE FIELD updated_at          ON TABLE calibration TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_calibration_org ON TABLE calibration FIELDS org UNIQUE;

-- ============================================================
-- ROI_EVENT — ROI tracking events
-- ============================================================
DEFINE TABLE roi_event SCHEMAFULL;
DEFINE FIELD org                       ON TABLE roi_event TYPE record<org>;
DEFINE FIELD event_type                ON TABLE roi_event TYPE string;
    -- mistake_prevented | knowledge_reused | gap_filled | connection_surfaced | correction_propagated
DEFINE FIELD task_id                   ON TABLE roi_event TYPE option<record<task>>;
DEFINE FIELD insight_ids               ON TABLE roi_event TYPE array DEFAULT [];
DEFINE FIELD estimated_time_saved_minutes ON TABLE roi_event TYPE int DEFAULT 0;
DEFINE FIELD description               ON TABLE roi_event TYPE string;
DEFINE FIELD created_at                ON TABLE roi_event TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_roi_org               ON TABLE roi_event FIELDS org, created_at;

-- ============================================================
-- Add calibrated_assessment field to task table
-- ============================================================
DEFINE FIELD calibrated_assessment ON TABLE task TYPE option<float>;

-- Bump schema version
UPSERT config_entry SET key = 'schema_version', value = '15'
    WHERE key = 'schema_version';
