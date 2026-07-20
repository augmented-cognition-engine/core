-- v041_initiative_lifecycle.surql
-- Add lifecycle timestamp fields to idea and initiative tables.
-- State machines and gate logic live in Python — no DB constraints on status values.

-- Idea lifecycle timestamps
DEFINE FIELD spec_id ON idea TYPE option<record<agent_spec>>;
DEFINE FIELD plan_id ON idea TYPE option<record<initiative>>;
DEFINE FIELD speccing_at ON idea TYPE option<datetime>;
DEFINE FIELD spec_review_at ON idea TYPE option<datetime>;
DEFINE FIELD planned_at ON idea TYPE option<datetime>;
DEFINE FIELD plan_review_at ON idea TYPE option<datetime>;

-- Initiative lifecycle timestamps
DEFINE FIELD decomposed_at ON initiative TYPE option<datetime>;
DEFINE FIELD ready_at ON initiative TYPE option<datetime>;
DEFINE FIELD completing_at ON initiative TYPE option<datetime>;
DEFINE FIELD reviewed_at ON initiative TYPE option<datetime>;
DEFINE FIELD blocked_at ON initiative TYPE option<datetime>;

-- Pending gate index (for fast /gates/pending queries)
-- No separate table — we query idea/initiative/milestone/work_item by status directly.

UPDATE config_entry:schema_version SET value = '041';
