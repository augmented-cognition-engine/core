-- schema/v107_world_model.surql
-- Phase C World Model: internal signal computation, scenario trees, counterfactual branches.

-- Internal signals computed from DB state (no external API)
-- source: "capability_decline" | "gap_persistence" | "decision_velocity_drop"
DEFINE TABLE signal SCHEMALESS;
DEFINE INDEX signal_product ON TABLE signal COLUMNS product;
DEFINE INDEX signal_kind    ON TABLE signal COLUMNS kind, created_at;

-- Scenario tree root (one per signal)
DEFINE TABLE scenario SCHEMALESS;
DEFINE INDEX scenario_product ON TABLE scenario COLUMNS product;

-- Individual branches within a scenario tree
DEFINE TABLE scenario_branch SCHEMALESS;
DEFINE INDEX scenario_branch_scenario ON TABLE scenario_branch COLUMNS scenario;

-- Medium-term constraints written by scenario_builder, read by planner at rollout time
DEFINE TABLE scenario_constraint SCHEMALESS;
DEFINE INDEX scenario_constraint_product ON TABLE scenario_constraint COLUMNS product, active;

-- Non-best rollout branches (TTL 7d); training negatives for future contrastive learning
DEFINE TABLE speculative_decision SCHEMALESS;
DEFINE INDEX speculative_product ON TABLE speculative_decision COLUMNS product, expires_at;

UPDATE config_entry SET value = '107' WHERE key = 'schema_version';
