-- v043: Composition memory + token efficiency tables

-- Composition signal: full composition tuple + outcomes per task
DEFINE TABLE composition_signal SCHEMAFULL;
DEFINE FIELD org ON composition_signal TYPE record<org>;
DEFINE FIELD task_id ON composition_signal TYPE record<task>;
DEFINE FIELD discipline ON composition_signal TYPE string;
DEFINE FIELD perspectives ON composition_signal TYPE array<string>;
DEFINE FIELD perspective_weights ON composition_signal TYPE object;
DEFINE FIELD perspective_weights.* ON composition_signal TYPE any;
DEFINE FIELD engagement_type ON composition_signal TYPE string;
DEFINE FIELD archetype ON composition_signal TYPE string;
DEFINE FIELD mode ON composition_signal TYPE string;
DEFINE FIELD complexity ON composition_signal TYPE string;
DEFINE FIELD specialties_loaded ON composition_signal TYPE array<string>;
DEFINE FIELD frameworks_used ON composition_signal TYPE option<array<string>>;
DEFINE FIELD skill_used ON composition_signal TYPE option<string>;
DEFINE FIELD utilization_rate ON composition_signal TYPE option<float>;
DEFINE FIELD feedback ON composition_signal TYPE option<string>;
DEFINE FIELD spin_count ON composition_signal TYPE int;
DEFINE FIELD adversarial_diversity ON composition_signal TYPE option<float>;
DEFINE FIELD token_input ON composition_signal TYPE int;
DEFINE FIELD token_output ON composition_signal TYPE int;
DEFINE FIELD token_total ON composition_signal TYPE int;
DEFINE FIELD token_delta ON composition_signal TYPE option<int>;
DEFINE FIELD estimated_tokens_saved ON composition_signal TYPE option<int>;
DEFINE FIELD created_at ON composition_signal TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_cs_org_discipline ON composition_signal FIELDS org, discipline, created_at;
DEFINE INDEX idx_cs_org_created ON composition_signal FIELDS org, created_at;
DEFINE INDEX idx_cs_task ON composition_signal FIELDS task_id UNIQUE;

-- Token baseline: experiment-derived estimates per discipline x complexity
DEFINE TABLE token_baseline SCHEMAFULL;
DEFINE FIELD org ON token_baseline TYPE record<org>;
DEFINE FIELD discipline ON token_baseline TYPE string;
DEFINE FIELD complexity ON token_baseline TYPE string;
DEFINE FIELD avg_tokens_control ON token_baseline TYPE int;
DEFINE FIELD avg_tokens_variant ON token_baseline TYPE int;
DEFINE FIELD sample_count ON token_baseline TYPE int;
DEFINE FIELD savings_pct ON token_baseline TYPE float;
DEFINE FIELD updated_at ON token_baseline TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_tb_unique ON token_baseline FIELDS org, discipline, complexity UNIQUE;

-- Token usage on task table (wildcard sub-fields for SCHEMAFULL compat, same as v035)
DEFINE FIELD token_usage ON task TYPE option<object>;
DEFINE FIELD token_usage.* ON task TYPE any;

UPSERT config_entry SET key = 'schema_version', value = '43'
    WHERE key = 'schema_version';
