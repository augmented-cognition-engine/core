-- I1-01: additive durable decision/correction receipt fields.
-- Existing task, decision, and observation rows are intentionally not
-- reconstructed from prose. Their public projections remain degraded until
-- structured facts are supplied through the supported write paths.

DEFINE FIELD IF NOT EXISTS decision_receipt ON TABLE task TYPE option<object>;
DEFINE FIELD IF NOT EXISTS human_disposition ON TABLE task TYPE option<object>;
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE task TYPE option<datetime>;

DEFINE FIELD IF NOT EXISTS selected_option ON TABLE decision TYPE option<string>;
DEFINE FIELD IF NOT EXISTS scope ON TABLE decision TYPE option<string>;
DEFINE FIELD IF NOT EXISTS assumptions ON TABLE decision TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS reconsideration_conditions ON TABLE decision TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS evidence_refs ON TABLE decision TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS originating_task ON TABLE decision TYPE option<record<task>>;
DEFINE FIELD IF NOT EXISTS originating_actor ON TABLE decision TYPE option<string>;
DEFINE FIELD IF NOT EXISTS provider ON TABLE decision TYPE option<string>;
DEFINE FIELD IF NOT EXISTS model ON TABLE decision TYPE option<string>;
DEFINE FIELD IF NOT EXISTS human_disposition ON TABLE decision TYPE option<object>;
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE decision TYPE option<datetime>;
DEFINE INDEX IF NOT EXISTS idx_decision_product_task ON TABLE decision FIELDS product, originating_task;

DEFINE FIELD IF NOT EXISTS source_surface ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS actor_ref ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS actor_class ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS content_hash ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS lifecycle_state ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS correction_contract_version ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS affected_decision ON TABLE observation TYPE option<record<decision>>;
DEFINE FIELD IF NOT EXISTS affected_task ON TABLE observation TYPE option<record<task>>;
DEFINE FIELD IF NOT EXISTS supersedes_correction ON TABLE observation TYPE option<record<observation>>;
DEFINE FIELD IF NOT EXISTS invalidates_correction ON TABLE observation TYPE option<record<observation>>;
DEFINE FIELD IF NOT EXISTS contests_correction ON TABLE observation TYPE option<record<observation>>;
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE observation TYPE option<datetime>;
DEFINE INDEX IF NOT EXISTS idx_observation_product_correction ON TABLE observation
    FIELDS product, observation_type, lifecycle_state, created_at;
