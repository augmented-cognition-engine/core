-- v010: skills engine — skill definitions with multi-step execution plans
-- Reference: docs/ace-03-architecture-spec.md §5

-- ============================================================
-- SKILL — reusable multi-step execution patterns
-- ============================================================
DEFINE TABLE skill SCHEMAFULL;
DEFINE FIELD org              ON TABLE skill TYPE option<record<org>>;
    -- null = built-in skill, record<org> = custom skill
DEFINE FIELD slug             ON TABLE skill TYPE string;
DEFINE FIELD name             ON TABLE skill TYPE string;
DEFINE FIELD description      ON TABLE skill TYPE string;
DEFINE FIELD domain_path      ON TABLE skill TYPE option<string>;
    -- domain scope; null = general-purpose
DEFINE FIELD tier             ON TABLE skill TYPE string;
    -- built-in | domain | custom
DEFINE FIELD steps            ON TABLE skill TYPE array;
    -- array of step objects: {name, archetype, mode, tools, output_format, description}
DEFINE FIELD activation_signals ON TABLE skill TYPE array;
    -- keyword list for skill selection matching
DEFINE FIELD created_at       ON TABLE skill TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_skill_slug   ON TABLE skill FIELDS org, slug UNIQUE;
DEFINE INDEX idx_skill_domain ON TABLE skill FIELDS org, domain_path;

-- ============================================================
-- SKILL_EXECUTION — per-task skill execution tracking
-- ============================================================
DEFINE TABLE skill_execution SCHEMAFULL;
DEFINE FIELD org              ON TABLE skill_execution TYPE record<org>;
DEFINE FIELD skill            ON TABLE skill_execution TYPE record<skill>;
DEFINE FIELD task             ON TABLE skill_execution TYPE record<task>;
DEFINE FIELD steps_completed  ON TABLE skill_execution TYPE int;
DEFINE FIELD total_duration_ms ON TABLE skill_execution TYPE int;
DEFINE FIELD step_results     ON TABLE skill_execution TYPE option<array>;
DEFINE FIELD feedback         ON TABLE skill_execution TYPE option<string>;
DEFINE FIELD created_at       ON TABLE skill_execution TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_skillexec    ON TABLE skill_execution FIELDS org, skill, created_at;

-- ============================================================
-- TASK — add skill_used field
-- ============================================================
DEFINE FIELD skill_used       ON TABLE task TYPE option<record<skill>>;

UPSERT config_entry SET key = 'schema_version', value = '10'
    WHERE key = 'schema_version';
