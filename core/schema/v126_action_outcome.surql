-- schema/v126_action_outcome.surql
-- Phase 3.2: the action active-loop. Every arm execution is recorded; a verified
-- build advances its spec to 'built' (arm-verified in a worktree, awaiting promotion).
DEFINE TABLE action_outcome SCHEMALESS;
DEFINE FIELD product          ON action_outcome TYPE record<product>;
DEFINE FIELD spec             ON action_outcome TYPE option<record<agent_spec>>;
DEFINE FIELD arm_domain       ON action_outcome TYPE string;
DEFINE FIELD intent           ON action_outcome TYPE string;
DEFINE FIELD passed           ON action_outcome TYPE bool;
DEFINE FIELD reason           ON action_outcome TYPE string;
DEFINE FIELD performed_verbs  ON action_outcome TYPE array<string>;
DEFINE FIELD diff_summary     ON action_outcome TYPE option<string>;
DEFINE FIELD workspace_branch ON action_outcome TYPE option<string>;
DEFINE FIELD created_at       ON action_outcome TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_ao_product_ts ON action_outcome FIELDS product, created_at;

-- Widen agent_spec.status to add 'built' (arm-verified, awaiting promotion).
REMOVE FIELD IF EXISTS status ON agent_spec;
DEFINE FIELD status ON agent_spec TYPE string
  DEFAULT 'draft'
  ASSERT $value INSIDE [
    'draft', 'approved', 'executing', 'verifying', 'completed', 'failed',
    'shipped', 'building', 'blocked', 'superseded', 'built'
  ];
