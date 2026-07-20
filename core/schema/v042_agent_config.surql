-- v042_agent_config.surql
-- Agent configuration overrides + annotation fields for graph nodes.

DEFINE TABLE agent_config_override SCHEMALESS;
DEFINE FIELD org ON agent_config_override TYPE record<org>;
DEFINE FIELD discipline ON agent_config_override TYPE string;
DEFINE FIELD forced_archetype ON agent_config_override TYPE option<string>;
DEFINE FIELD forced_mode ON agent_config_override TYPE option<string>;
DEFINE FIELD forced_perspective ON agent_config_override TYPE option<string>;
DEFINE FIELD max_spins ON agent_config_override TYPE option<int>;
DEFINE FIELD disabled_frameworks ON agent_config_override TYPE option<array>;
DEFINE FIELD created_at ON agent_config_override TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_aco_org ON agent_config_override FIELDS org, discipline;

-- Annotation field on major node tables
DEFINE FIELD annotation ON graph_file TYPE option<string>;
DEFINE FIELD annotation ON capability TYPE option<string>;
DEFINE FIELD annotation ON idea TYPE option<string>;
DEFINE FIELD annotation ON initiative TYPE option<string>;
DEFINE FIELD annotation ON task TYPE option<string>;
DEFINE FIELD annotation ON decision TYPE option<string>;

UPDATE config_entry:schema_version SET value = '042';
