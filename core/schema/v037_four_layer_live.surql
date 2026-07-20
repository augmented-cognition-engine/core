-- v037_four_layer_live.surql
-- Four-Layer Graph Architecture: LIVE layer tables, cross-layer edges, resource_lock migration

-- ============================================================
-- LIVE LAYER: agent_session
-- ============================================================
DEFINE TABLE agent_session SCHEMAFULL;
DEFINE FIELD org ON agent_session TYPE record<org>;
DEFINE FIELD work_item ON agent_session TYPE option<record<work_item>>;
DEFINE FIELD user ON agent_session TYPE option<record<user>>;
DEFINE FIELD state ON agent_session TYPE string DEFAULT 'starting'
  ASSERT $value IN ['starting', 'active', 'blocked', 'completing', 'done', 'failed', 'abandoned'];
DEFINE FIELD started_at ON agent_session TYPE datetime DEFAULT time::now();
DEFINE FIELD last_heartbeat ON agent_session TYPE datetime DEFAULT time::now();
DEFINE FIELD files_claimed ON agent_session TYPE array DEFAULT [];
DEFINE FIELD capabilities_touched ON agent_session TYPE array DEFAULT [];
DEFINE FIELD progress_pct ON agent_session TYPE option<int>;
DEFINE FIELD error ON agent_session TYPE option<string>;
DEFINE FIELD completed_at ON agent_session TYPE option<datetime>;
DEFINE FIELD context ON agent_session TYPE option<object> FLEXIBLE;
DEFINE INDEX idx_as_org ON agent_session FIELDS org;
DEFINE INDEX idx_as_state ON agent_session FIELDS org, state;

-- ============================================================
-- LIVE LAYER: active_edit
-- ============================================================
DEFINE TABLE active_edit SCHEMAFULL;
DEFINE FIELD org ON active_edit TYPE record<org>;
DEFINE FIELD agent_session ON active_edit TYPE record<agent_session>;
DEFINE FIELD file ON active_edit TYPE record<graph_file>;
DEFINE FIELD branch ON active_edit TYPE option<string>;
DEFINE FIELD state ON active_edit TYPE string DEFAULT 'claimed'
  ASSERT $value IN ['claimed', 'editing', 'committing', 'released', 'conflict', 'resolved', 'abandoned'];
DEFINE FIELD claimed_at ON active_edit TYPE datetime DEFAULT time::now();
DEFINE FIELD lines_start ON active_edit TYPE option<int>;
DEFINE FIELD lines_end ON active_edit TYPE option<int>;
DEFINE FIELD released_at ON active_edit TYPE option<datetime>;
DEFINE INDEX idx_ae_org ON active_edit FIELDS org;
DEFINE INDEX idx_ae_file ON active_edit FIELDS org, file, state;
DEFINE INDEX idx_ae_session ON active_edit FIELDS agent_session;

-- ============================================================
-- WORK LAYER: agent_execution (renamed from graph_agent)
-- ============================================================
DEFINE TABLE agent_execution SCHEMALESS;
DEFINE FIELD org ON agent_execution TYPE option<record<org>>;
DEFINE FIELD archetype ON agent_execution TYPE option<string>;
DEFINE FIELD mode ON agent_execution TYPE option<string>;
DEFINE FIELD perspective ON agent_execution TYPE option<string>;
DEFINE FIELD specialties ON agent_execution TYPE option<array>;
DEFINE FIELD graph_id ON agent_execution TYPE option<string>;
DEFINE FIELD created_at ON agent_execution TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_aex_org ON agent_execution FIELDS org;

-- ============================================================
-- CROSS-LAYER RELATION EDGES
-- ============================================================

-- LIVE -> PRODUCT: agent working on capability
DEFINE TABLE touches SCHEMAFULL;
DEFINE FIELD in ON touches TYPE record<agent_session>;
DEFINE FIELD out ON touches TYPE record<capability>;
DEFINE FIELD created_at ON touches TYPE datetime DEFAULT time::now();

-- LIVE -> CODE: file being edited
DEFINE TABLE editing SCHEMAFULL;
DEFINE FIELD in ON editing TYPE record<active_edit>;
DEFINE FIELD out ON editing TYPE record<graph_file>;
DEFINE FIELD created_at ON editing TYPE datetime DEFAULT time::now();

-- LIVE -> WORK: agent running work item
DEFINE TABLE executes SCHEMAFULL;
DEFINE FIELD in ON executes TYPE record<agent_session>;
DEFINE FIELD out ON executes TYPE record<work_item>;
DEFINE FIELD created_at ON executes TYPE datetime DEFAULT time::now();

-- WORK -> PRODUCT: task fixing gap
DEFINE TABLE addresses SCHEMAFULL;
DEFINE FIELD in ON addresses TYPE record;
DEFINE FIELD out ON addresses TYPE record<capability_quality>;
DEFINE FIELD created_at ON addresses TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_addr_out ON addresses FIELDS out;

-- WORK -> WORK: initiative decomposes into milestones, milestones into work_items
DEFINE TABLE IF NOT EXISTS decomposes SCHEMALESS;

-- WORK -> CROSS-CUTTING: work_item assigned to user
DEFINE TABLE IF NOT EXISTS assigned_to SCHEMALESS;

-- ============================================================
-- MIGRATE graph_agent DATA TO agent_execution
-- ============================================================
INSERT INTO agent_execution SELECT * FROM graph_agent;

-- ============================================================
-- RESOURCE_LOCK MIGRATION: add state field
-- ============================================================
DEFINE FIELD state ON resource_lock TYPE string DEFAULT 'held'
  ASSERT $value IN ['acquired', 'held', 'releasing', 'released', 'stolen', 'expired'];
DEFINE FIELD acquired_at ON resource_lock TYPE option<datetime>;
DEFINE FIELD released_at ON resource_lock TYPE option<datetime>;
DEFINE FIELD stolen_by ON resource_lock TYPE option<string>;
DEFINE FIELD expires_at ON resource_lock TYPE option<datetime>;

-- ============================================================
-- FORMALIZE frontend_dep
-- ============================================================
DEFINE TABLE IF NOT EXISTS frontend_dep SCHEMALESS;

-- ============================================================
-- UPDATE SCHEMA VERSION
-- ============================================================
UPDATE config_entry:schema_version SET value = '037';
