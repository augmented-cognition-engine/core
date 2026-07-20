-- v040_connected_graph.surql
-- Decision table + 12 RELATION tables for cross-layer graph connectivity

-- Decision node table (PRODUCT layer — PM-level choices)
DEFINE TABLE decision SCHEMALESS;
DEFINE FIELD org ON decision TYPE record<org>;
DEFINE FIELD title ON decision TYPE string;
DEFINE FIELD decision_type ON decision TYPE string
  ASSERT $value IN ['architecture', 'prioritization', 'trade_off', 'direction', 'rejection', 'convention'];
DEFINE FIELD rationale ON decision TYPE string;
DEFINE FIELD alternatives ON decision TYPE option<array>;
DEFINE FIELD outcome ON decision TYPE string DEFAULT 'accepted'
  ASSERT $value IN ['accepted', 'rejected', 'superseded', 'pending'];
DEFINE FIELD source ON decision TYPE option<string>;
DEFINE FIELD source_session ON decision TYPE option<record<chat_session>>;
DEFINE FIELD created_at ON decision TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_decision_org ON decision FIELDS org;
DEFINE INDEX idx_decision_type ON decision FIELDS org, decision_type;

-- Story edges
DEFINE TABLE inspired_by TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON inspired_by TYPE record<idea>;
DEFINE FIELD out ON inspired_by TYPE record<insight>;

DEFINE TABLE became TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON became TYPE record<initiative>;
DEFINE FIELD out ON became TYPE record<idea>;

DEFINE TABLE specified_by TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON specified_by TYPE record<agent_spec>;
DEFINE FIELD out ON specified_by TYPE record;

DEFINE TABLE fulfills TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON fulfills TYPE record<task>;
DEFINE FIELD out ON fulfills TYPE record<agent_spec>;

DEFINE TABLE led_to TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON led_to TYPE record<decision>;
DEFINE FIELD out ON led_to TYPE record;

-- Provenance edges (in accepts both decision and graph_decision)
DEFINE TABLE affected TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON affected TYPE record;
DEFINE FIELD out ON affected TYPE record<capability>;

DEFINE TABLE derived_from TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON derived_from TYPE record<insight>;
DEFINE FIELD out ON derived_from TYPE record<observation>;

DEFINE TABLE supersedes TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON supersedes TYPE record<decision>;
DEFINE FIELD out ON supersedes TYPE record<decision>;

-- Context edges
DEFINE TABLE loaded TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON loaded TYPE record;
DEFINE FIELD out ON loaded TYPE record;

-- Outcome edges
DEFINE TABLE quality_delta TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON quality_delta TYPE record;
DEFINE FIELD out ON quality_delta TYPE record<capability_quality>;
DEFINE FIELD before_score ON quality_delta TYPE option<float>;
DEFINE FIELD after_score ON quality_delta TYPE option<float>;
DEFINE FIELD delta ON quality_delta TYPE option<float>;
DEFINE FIELD closed_gap ON quality_delta TYPE option<bool>;

-- Backlog edges
DEFINE TABLE targets TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON targets TYPE record;
DEFINE FIELD out ON targets TYPE record<capability>;

DEFINE TABLE blocked_by TYPE RELATION SCHEMALESS;
DEFINE FIELD in ON blocked_by TYPE record<initiative>;
DEFINE FIELD out ON blocked_by TYPE record<initiative>;

UPDATE config_entry:schema_version SET value = '040';
