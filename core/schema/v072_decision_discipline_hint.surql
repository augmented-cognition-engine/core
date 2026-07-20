-- v072: add discipline_hint field + index to decision table
-- Enables discipline-matched decision retrieval in the orchestrator loader.
-- Decisions now surface relevant prior architectural/product choices when the
-- same discipline is active — resolving the recency-only retrieval gap.
DEFINE FIELD discipline_hint ON TABLE decision TYPE option<string>;
DEFINE INDEX idx_decision_discipline ON TABLE decision FIELDS product, discipline_hint, outcome;

UPDATE config_entry SET value = '72' WHERE key = 'schema_version';
