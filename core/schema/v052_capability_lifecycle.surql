-- v051: Capability lifecycle conductor
-- Lifecycle tracks per capability x dimension, conductor rules,
-- quality templates, and rule execution log.

-- Lifecycle tracks
DEFINE TABLE capability_lifecycle_track SCHEMALESS;
DEFINE FIELD org               ON capability_lifecycle_track TYPE record<org>;
DEFINE FIELD capability        ON capability_lifecycle_track TYPE record<capability>;
DEFINE FIELD dimension         ON capability_lifecycle_track TYPE string;
DEFINE FIELD state             ON capability_lifecycle_track TYPE string
  ASSERT $value IN [
    'unassessed', 'gap_identified', 'spec_pending', 'spec_review',
    'executing', 'verifying', 'needs_rework', 'met', 'exceeded'
  ];
DEFINE FIELD current_score     ON capability_lifecycle_track TYPE option<float>;
DEFINE FIELD target_score      ON capability_lifecycle_track TYPE option<float>;
DEFINE FIELD active_spec_id    ON capability_lifecycle_track TYPE option<record<agent_spec>>;
DEFINE FIELD attempt_count     ON capability_lifecycle_track TYPE int DEFAULT 0;
DEFINE FIELD last_transition   ON capability_lifecycle_track TYPE datetime DEFAULT time::now();
DEFINE FIELD stuck_since       ON capability_lifecycle_track TYPE option<datetime>;
DEFINE FIELD metadata          ON capability_lifecycle_track TYPE option<object> FLEXIBLE;
DEFINE INDEX idx_clt_cap_dim   ON capability_lifecycle_track FIELDS capability, dimension UNIQUE;
DEFINE INDEX idx_clt_state     ON capability_lifecycle_track FIELDS org, state;
DEFINE INDEX idx_clt_stuck     ON capability_lifecycle_track FIELDS org, stuck_since;

-- Conductor rules (declarative, per-org)
DEFINE TABLE conductor_rule SCHEMALESS;
DEFINE FIELD org              ON conductor_rule TYPE option<record<org>>;
DEFINE FIELD name             ON conductor_rule TYPE string;
DEFINE FIELD description      ON conductor_rule TYPE string;
DEFINE FIELD enabled          ON conductor_rule TYPE bool DEFAULT true;
DEFINE FIELD priority         ON conductor_rule TYPE int DEFAULT 100;
DEFINE FIELD trigger_event    ON conductor_rule TYPE string;
DEFINE FIELD conditions       ON conductor_rule TYPE array;
DEFINE FIELD actions          ON conductor_rule TYPE array;
DEFINE FIELD cooldown_seconds ON conductor_rule TYPE int DEFAULT 0;
DEFINE FIELD version          ON conductor_rule TYPE int DEFAULT 1;
DEFINE FIELD source           ON conductor_rule TYPE string DEFAULT 'system';
DEFINE FIELD experiment_id    ON conductor_rule TYPE option<string>;
DEFINE FIELD metrics          ON conductor_rule TYPE option<object> FLEXIBLE;
DEFINE FIELD created_at       ON conductor_rule TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at       ON conductor_rule TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_rule_trigger  ON conductor_rule FIELDS trigger_event, enabled;
DEFINE INDEX idx_rule_org      ON conductor_rule FIELDS org, name UNIQUE;

-- Quality templates (layered inheritance)
DEFINE TABLE quality_template SCHEMALESS;
DEFINE FIELD org               ON quality_template TYPE option<record<org>>;
DEFINE FIELD scope             ON quality_template TYPE string
  ASSERT $value IN ['universal', 'org', 'project', 'capability_type'];
DEFINE FIELD scope_value       ON quality_template TYPE option<string>;
DEFINE FIELD dimension         ON quality_template TYPE string;
DEFINE FIELD threshold         ON quality_template TYPE float;
DEFINE FIELD stretch_target    ON quality_template TYPE option<float>;
DEFINE FIELD weight            ON quality_template TYPE float DEFAULT 1.0;
DEFINE FIELD checklist         ON quality_template TYPE option<array>;
DEFINE FIELD auto_assess       ON quality_template TYPE bool DEFAULT true;
DEFINE FIELD active            ON quality_template TYPE bool DEFAULT true;
DEFINE FIELD source            ON quality_template TYPE string DEFAULT 'system';
DEFINE FIELD created_at        ON quality_template TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_qt_scope      ON quality_template FIELDS org, scope, scope_value, dimension UNIQUE;
DEFINE INDEX idx_qt_org        ON quality_template FIELDS org, dimension;

-- Rule execution log (for experimentation)
DEFINE TABLE conductor_rule_execution SCHEMALESS;
DEFINE FIELD org           ON conductor_rule_execution TYPE record<org>;
DEFINE FIELD rule_id       ON conductor_rule_execution TYPE record<conductor_rule>;
DEFINE FIELD experiment_id ON conductor_rule_execution TYPE option<string>;
DEFINE FIELD trigger_event ON conductor_rule_execution TYPE string;
DEFINE FIELD track_id      ON conductor_rule_execution TYPE option<record<capability_lifecycle_track>>;
DEFINE FIELD outcome       ON conductor_rule_execution TYPE option<string>;
DEFINE FIELD duration_ms   ON conductor_rule_execution TYPE int DEFAULT 0;
DEFINE FIELD created_at    ON conductor_rule_execution TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_cre_rule  ON conductor_rule_execution FIELDS rule_id, created_at;
DEFINE INDEX idx_cre_exp   ON conductor_rule_execution FIELDS experiment_id, created_at;

UPSERT config_entry SET value = 'v052'
  WHERE key = 'schema_version';
