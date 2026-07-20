-- schema/v125_agent_spec_strategy_status.surql
-- Widen agent_spec.status to include strategy-lifecycle values used by strategy_ingest.
-- strategy_ingest writes: shipped | building | draft | blocked | superseded
-- Prior schema only allowed: draft | approved | executing | verifying | completed | failed
-- Also: make org optional (product-level specs have no org context).
-- REMOVE + DEFINE required to replace an existing ASSERT constraint in SurrealDB v3.
REMOVE FIELD IF EXISTS status ON agent_spec;
DEFINE FIELD status ON agent_spec TYPE string
  DEFAULT 'draft'
  ASSERT $value INSIDE [
    'draft', 'approved', 'executing', 'verifying', 'completed', 'failed',
    'shipped', 'building', 'blocked', 'superseded'
  ];
REMOVE FIELD IF EXISTS org ON agent_spec;
DEFINE FIELD org ON agent_spec TYPE option<record<org>>;
