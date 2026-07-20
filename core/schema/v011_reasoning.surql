-- v011: reasoning framework engine
-- Reference: docs/framework_library.md (Doc 24)

-- ============================================================
-- FRAMEWORK — reasoning framework definitions
-- ============================================================
DEFINE TABLE framework SCHEMAFULL;
DEFINE FIELD org               ON TABLE framework TYPE option<record<org>>;
    -- null = built-in, record<org> = org-specific
DEFINE FIELD slug              ON TABLE framework TYPE string;
DEFINE FIELD name              ON TABLE framework TYPE string;
DEFINE FIELD family            ON TABLE framework TYPE string;
    -- diagnostic | systemic | generative | evaluative | predictive | adversarial
DEFINE FIELD tier              ON TABLE framework TYPE string;
    -- built-in | domain | advanced
DEFINE FIELD description       ON TABLE framework TYPE string;
DEFINE FIELD system_prompt     ON TABLE framework TYPE string;
DEFINE FIELD activation_signals ON TABLE framework TYPE array;
DEFINE FIELD archetype_affinity ON TABLE framework TYPE object;
    -- { analyst: 0.9, researcher: 0.8, ... }
DEFINE FIELD mode_affinity     ON TABLE framework TYPE object;
    -- { deliberative: 0.9, exploratory: 0.8, ... }
DEFINE FIELD composability     ON TABLE framework TYPE object;
    -- { conflicts: ["slug1"], complements: ["slug2"] }
DEFINE FIELD created_at        ON TABLE framework TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_fw_slug       ON TABLE framework FIELDS org, slug UNIQUE;
DEFINE INDEX idx_fw_family     ON TABLE framework FIELDS org, family;

-- ============================================================
-- FRAMEWORK_PERF — per-framework performance tracking
-- ============================================================
DEFINE TABLE framework_perf SCHEMAFULL;
DEFINE FIELD framework         ON TABLE framework_perf TYPE record<framework>;
DEFINE FIELD org               ON TABLE framework_perf TYPE record<org>;
DEFINE FIELD task_count        ON TABLE framework_perf TYPE int DEFAULT 0;
DEFINE FIELD accept_rate       ON TABLE framework_perf TYPE float DEFAULT 0.0;
DEFINE FIELD avg_score         ON TABLE framework_perf TYPE float DEFAULT 0.0;
DEFINE FIELD last_used         ON TABLE framework_perf TYPE option<datetime>;
DEFINE INDEX idx_fwperf        ON TABLE framework_perf FIELDS framework, org UNIQUE;

-- ============================================================
-- TASK — add strategies_used field
-- ============================================================
DEFINE FIELD strategies_used   ON TABLE task TYPE option<array>;

UPSERT config_entry SET key = 'schema_version', value = '11'
    WHERE key = 'schema_version';
