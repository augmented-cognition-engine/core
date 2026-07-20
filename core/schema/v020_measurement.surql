-- schema/v020_measurement.surql
-- Measurement tables for IPM tracking, experiment logging, and calibration.
-- Spec: docs/superpowers/specs/2026-03-23-ipm-measurement-design.md

-- === IPM fields on task table ===
DEFINE FIELD ipm_score       ON TABLE task TYPE option<float>;
DEFINE FIELD ipm_vector      ON TABLE task TYPE option<object>;
DEFINE FIELD ipm_baseline    ON TABLE task TYPE option<float>;

-- === Experiment log (the moat) ===
DEFINE TABLE experiment_log SCHEMAFULL;
DEFINE FIELD org             ON experiment_log TYPE record<org>;
DEFINE FIELD domain_path     ON experiment_log TYPE string;
DEFINE FIELD variant_desc    ON experiment_log TYPE string;
DEFINE FIELD change_type     ON experiment_log TYPE string;
DEFINE FIELD control_mean    ON experiment_log TYPE float;
DEFINE FIELD variant_mean    ON experiment_log TYPE float;
DEFINE FIELD improvement     ON experiment_log TYPE float;
DEFINE FIELD effect_size_d   ON experiment_log TYPE float;
DEFINE FIELD p_value         ON experiment_log TYPE float;
DEFINE FIELD significant     ON experiment_log TYPE bool;
DEFINE FIELD committed       ON experiment_log TYPE bool;
DEFINE FIELD commit_sha      ON experiment_log TYPE option<string>;
DEFINE FIELD reverted        ON experiment_log TYPE bool DEFAULT false;
DEFINE FIELD cost            ON experiment_log TYPE float DEFAULT 0.0;
DEFINE FIELD task_count      ON experiment_log TYPE int;
DEFINE FIELD created_at      ON experiment_log TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_exp_log     ON TABLE experiment_log FIELDS org, domain_path, created_at;

-- === Daily metrics (precomputed for dashboard) ===
DEFINE TABLE daily_metrics SCHEMAFULL;
DEFINE FIELD org             ON daily_metrics TYPE record<org>;
DEFINE FIELD date            ON daily_metrics TYPE datetime;
DEFINE FIELD tasks_total     ON daily_metrics TYPE int;
DEFINE FIELD tasks_grounded  ON daily_metrics TYPE int;
DEFINE FIELD avg_quality     ON daily_metrics TYPE option<float>;
DEFINE FIELD ipm_scalar      ON daily_metrics TYPE option<float>;
DEFINE FIELD ipm_vector      ON daily_metrics TYPE option<object>;
DEFINE FIELD feedback_rate   ON daily_metrics TYPE float;
DEFINE FIELD ece             ON daily_metrics TYPE option<float>;
DEFINE FIELD token_cost_live ON daily_metrics TYPE float DEFAULT 0.0;
DEFINE FIELD token_cost_measurement ON daily_metrics TYPE float DEFAULT 0.0;
DEFINE FIELD experiments_run ON daily_metrics TYPE int DEFAULT 0;
DEFINE FIELD experiments_committed ON daily_metrics TYPE int DEFAULT 0;
DEFINE FIELD created_at      ON daily_metrics TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_daily       ON TABLE daily_metrics FIELDS org, date UNIQUE;

-- === Calibration snapshots (weekly) ===
DEFINE TABLE calibration_snapshot SCHEMAFULL;
DEFINE FIELD org             ON calibration_snapshot TYPE record<org>;
DEFINE FIELD computed_at     ON calibration_snapshot TYPE datetime;
DEFINE FIELD ece             ON calibration_snapshot TYPE float;
DEFINE FIELD brier_score     ON calibration_snapshot TYPE float;
DEFINE FIELD buckets         ON calibration_snapshot TYPE object;
DEFINE FIELD sample_size     ON calibration_snapshot TYPE int;
DEFINE INDEX idx_cal         ON TABLE calibration_snapshot FIELDS org, computed_at;

-- === Schema version ===
UPDATE config_entry SET value = '20' WHERE key = 'schema_version';
