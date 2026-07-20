-- v032_product_awareness.surql
-- Product Awareness Layer: capability map, quality assessments, product direction,
-- questions, answers, agent specs, feedback, scan state.
-- PURELY ADDITIVE — no existing tables modified.

-- ================================================================
-- PRODUCT MAP
-- ================================================================

DEFINE TABLE capability SCHEMAFULL;
DEFINE FIELD org ON capability TYPE record<org>;
DEFINE FIELD name ON capability TYPE string;
DEFINE FIELD slug ON capability TYPE string;
DEFINE FIELD description ON capability TYPE string;
DEFINE FIELD status ON capability TYPE string
  ASSERT $value IN ['planned', 'building', 'built', 'partial', 'deprecated', 'missing'];
DEFINE FIELD intent ON capability TYPE option<object>;
DEFINE FIELD reality ON capability TYPE option<object>;
DEFINE FIELD parent ON capability TYPE option<record<capability>>;
DEFINE FIELD priority ON capability TYPE option<string>
  ASSERT $value IN ['critical', 'important', 'nice_to_have'];
DEFINE FIELD tags ON capability TYPE option<array<string>>;
DEFINE FIELD created_at ON capability TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON capability TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_capability_org ON capability FIELDS org;
DEFINE INDEX idx_capability_org_slug ON capability FIELDS org, slug UNIQUE;
DEFINE INDEX idx_capability_status ON capability FIELDS org, status;

-- ================================================================
-- QUALITY ASSESSMENTS (normalized for queryability)
-- ================================================================

DEFINE TABLE capability_quality SCHEMAFULL;
DEFINE FIELD capability ON capability_quality TYPE record<capability>;
DEFINE FIELD org ON capability_quality TYPE record<org>;
DEFINE FIELD dimension ON capability_quality TYPE string;
DEFINE FIELD score ON capability_quality TYPE float;
DEFINE FIELD gaps ON capability_quality TYPE option<array<string>>;
DEFINE FIELD evidence ON capability_quality TYPE option<array<string>>;
DEFINE FIELD assessed_at ON capability_quality TYPE datetime DEFAULT time::now();
DEFINE FIELD assessed_by ON capability_quality TYPE string;
DEFINE INDEX idx_cq_capability ON capability_quality FIELDS capability;
DEFINE INDEX idx_cq_org_dim ON capability_quality FIELDS org, dimension;
DEFINE INDEX idx_cq_org_dim_cap ON capability_quality FIELDS org, dimension, capability UNIQUE;

-- ================================================================
-- EDGE TYPES
-- ================================================================

-- Capability Dependencies (RELATION, consistent with v031 edges)
DEFINE TABLE capability_dep TYPE RELATION SCHEMAFULL;
DEFINE FIELD dep_type ON capability_dep TYPE string
  ASSERT $value IN ['requires', 'enhances', 'replaces', 'conflicts'];
DEFINE FIELD evidence ON capability_dep TYPE option<string>;
DEFINE FIELD created_at ON capability_dep TYPE datetime DEFAULT time::now();

-- Code-to-Capability bridge (RELATION: graph_file -> realizes -> capability)
DEFINE TABLE realizes TYPE RELATION SCHEMAFULL;
DEFINE FIELD confidence ON realizes TYPE float DEFAULT 1.0;
DEFINE FIELD file_glob ON realizes TYPE option<string>;
DEFINE FIELD source ON realizes TYPE option<string>;
DEFINE FIELD created_at ON realizes TYPE datetime DEFAULT time::now();

-- ================================================================
-- PRODUCT DIRECTION
-- ================================================================

DEFINE TABLE product_direction SCHEMAFULL;
DEFINE FIELD org ON product_direction TYPE record<org>;
DEFINE FIELD name ON product_direction TYPE string;
DEFINE FIELD description ON product_direction TYPE string;
DEFINE FIELD goals ON product_direction TYPE option<array<object>>;
DEFINE FIELD active ON product_direction TYPE bool DEFAULT true;
DEFINE FIELD supersedes ON product_direction TYPE option<record<product_direction>>;
DEFINE FIELD created_at ON product_direction TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON product_direction TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_direction_org ON product_direction FIELDS org;
DEFINE INDEX idx_direction_active ON product_direction FIELDS org, active;

-- ================================================================
-- PRODUCT QUESTIONS
-- ================================================================

DEFINE TABLE product_question SCHEMAFULL;
DEFINE FIELD org ON product_question TYPE record<org>;
DEFINE FIELD question ON product_question TYPE string;
DEFINE FIELD category ON product_question TYPE string
  ASSERT $value IN ['inward', 'downward', 'outward', 'forward', 'temporal'];
DEFINE FIELD source ON product_question TYPE string;
DEFINE FIELD capability ON product_question TYPE option<record<capability>>;
DEFINE FIELD priority ON product_question TYPE string
  ASSERT $value IN ['critical', 'high', 'medium', 'low'];
DEFINE FIELD status ON product_question TYPE string DEFAULT 'open'
  ASSERT $value IN ['open', 'researching', 'answered', 'acted_on', 'dismissed'];
DEFINE FIELD created_at ON product_question TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_pq_org_status ON product_question FIELDS org, status;
DEFINE INDEX idx_pq_org_category ON product_question FIELDS org, category;
DEFINE INDEX idx_pq_capability ON product_question FIELDS capability;

-- Question Answers (separate for history)
DEFINE TABLE product_answer SCHEMAFULL;
DEFINE FIELD question ON product_answer TYPE record<product_question>;
DEFINE FIELD org ON product_answer TYPE record<org>;
DEFINE FIELD content ON product_answer TYPE string;
DEFINE FIELD evidence ON product_answer TYPE option<array<string>>;
DEFINE FIELD confidence ON product_answer TYPE float DEFAULT 0.5;
DEFINE FIELD recommendations ON product_answer TYPE option<array<object>>;
DEFINE FIELD answered_by ON product_answer TYPE string;
DEFINE FIELD created_at ON product_answer TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_pa_question ON product_answer FIELDS question;

-- ================================================================
-- ACTIVE DISCIPLINES
-- ================================================================

DEFINE TABLE active_discipline SCHEMAFULL;
DEFINE FIELD org ON active_discipline TYPE record<org>;
DEFINE FIELD discipline ON active_discipline TYPE string;
DEFINE FIELD active ON active_discipline TYPE bool DEFAULT true;
DEFINE FIELD activated_at ON active_discipline TYPE datetime DEFAULT time::now();
DEFINE FIELD reason ON active_discipline TYPE option<string>;
DEFINE INDEX idx_ad_org ON active_discipline FIELDS org;
DEFINE INDEX idx_ad_org_disc ON active_discipline FIELDS org, discipline UNIQUE;

-- ================================================================
-- AGENT SPECS (agentic PM)
-- ================================================================

DEFINE TABLE agent_spec SCHEMALESS;
DEFINE FIELD org ON agent_spec TYPE record<org>;
DEFINE FIELD capability ON agent_spec TYPE option<record<capability>>;
DEFINE FIELD source ON agent_spec TYPE string;
DEFINE FIELD source_id ON agent_spec TYPE option<string>;
DEFINE FIELD objective ON agent_spec TYPE string;
DEFINE FIELD context ON agent_spec TYPE option<object>;
DEFINE FIELD acceptance_criteria ON agent_spec TYPE array<object>;
DEFINE FIELD acceptance_criteria.* ON agent_spec TYPE object;
DEFINE FIELD constraints ON agent_spec TYPE option<array<string>>;
DEFINE FIELD integration_points ON agent_spec TYPE option<array<object>>;
DEFINE FIELD estimated_files ON agent_spec TYPE option<array<string>>;
DEFINE FIELD test_requirements ON agent_spec TYPE option<array<string>>;
DEFINE FIELD best_practices ON agent_spec TYPE option<array<string>>;
DEFINE FIELD status ON agent_spec TYPE string DEFAULT 'draft'
  ASSERT $value IN ['draft', 'approved', 'executing', 'verifying', 'completed', 'failed'];
DEFINE FIELD created_at ON agent_spec TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON agent_spec TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_spec_org ON agent_spec FIELDS org;
DEFINE INDEX idx_spec_status ON agent_spec FIELDS org, status;
DEFINE INDEX idx_spec_capability ON agent_spec FIELDS capability;

-- ================================================================
-- AGENT FEEDBACK
-- ================================================================

DEFINE TABLE agent_feedback SCHEMALESS;
DEFINE FIELD org ON agent_feedback TYPE record<org>;
DEFINE FIELD spec ON agent_feedback TYPE record<agent_spec>;
DEFINE FIELD work_unit ON agent_feedback TYPE option<string>;
DEFINE FIELD feedback_type ON agent_feedback TYPE string
  ASSERT $value IN ['blocker', 'discovery', 'trade_off', 'scope_question', 'completion', 'progress'];
DEFINE FIELD content ON agent_feedback TYPE string;
DEFINE FIELD context ON agent_feedback TYPE option<object>;
DEFINE FIELD resolved ON agent_feedback TYPE bool DEFAULT false;
DEFINE FIELD resolution ON agent_feedback TYPE option<string>;
DEFINE FIELD created_at ON agent_feedback TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_af_spec ON agent_feedback FIELDS spec;
DEFINE INDEX idx_af_org_type ON agent_feedback FIELDS org, feedback_type;
DEFINE INDEX idx_af_unresolved ON agent_feedback FIELDS org, resolved;

-- ================================================================
-- CAPABILITY SCAN STATE
-- ================================================================

DEFINE TABLE capability_scan SCHEMAFULL;
DEFINE FIELD org ON capability_scan TYPE record<org>;
DEFINE FIELD scan_type ON capability_scan TYPE string
  ASSERT $value IN ['bootstrap', 'incremental'];
DEFINE FIELD status ON capability_scan TYPE string
  ASSERT $value IN ['running', 'completed', 'failed'];
DEFINE FIELD capabilities_proposed ON capability_scan TYPE option<int>;
DEFINE FIELD capabilities_confirmed ON capability_scan TYPE option<int>;
DEFINE FIELD files_mapped ON capability_scan TYPE option<int>;
DEFINE FIELD duration_ms ON capability_scan TYPE option<int>;
DEFINE FIELD error ON capability_scan TYPE option<string>;
DEFINE FIELD created_at ON capability_scan TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_capscan_org ON capability_scan FIELDS org;

-- Bump schema version
UPSERT config_entry SET value = '32' WHERE key = 'schema_version';

-- Fix: make reality and intent FLEXIBLE for nested objects
REMOVE FIELD reality ON capability;
DEFINE FIELD reality ON capability TYPE option<object> FLEXIBLE;
REMOVE FIELD intent ON capability;
DEFINE FIELD intent ON capability TYPE option<object> FLEXIBLE;
