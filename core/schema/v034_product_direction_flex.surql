-- v034: Convert PM tables from SCHEMAFULL to SCHEMALESS
-- SurrealDB v3 SCHEMAFULL rejects nested object fields in arrays
-- unless every sub-field is pre-defined. These tables store
-- variable-shape objects, so SCHEMALESS is the correct approach.
-- REMOVE + DEFINE is required because SurrealDB cannot ALTER table type.

-- product_direction: goals contain {goal, priority, status, ...}
REMOVE TABLE IF EXISTS product_direction;
DEFINE TABLE product_direction SCHEMALESS;
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

-- work_item: review_stages contain {dimension, passed, issues}
REMOVE TABLE IF EXISTS work_item;
DEFINE TABLE work_item SCHEMALESS;
DEFINE FIELD org ON work_item TYPE record<org>;
DEFINE FIELD milestone ON work_item TYPE record<milestone>;
DEFINE FIELD initiative ON work_item TYPE record<initiative>;
DEFINE FIELD title ON work_item TYPE string;
DEFINE FIELD description ON work_item TYPE string;
DEFINE FIELD archetype ON work_item TYPE string;
DEFINE FIELD mode ON work_item TYPE string;
DEFINE FIELD skill ON work_item TYPE option<string>;
DEFINE FIELD domain_path ON work_item TYPE string;
DEFINE FIELD tasks ON work_item TYPE array DEFAULT [];
DEFINE FIELD depends_on ON work_item TYPE option<array>;
DEFINE FIELD parallel_group ON work_item TYPE option<int>;
DEFINE FIELD assigned_to ON work_item TYPE option<record<user>>;
DEFINE FIELD requires_human ON work_item TYPE bool DEFAULT false;
DEFINE FIELD handoff_from ON work_item TYPE option<record<user>>;
DEFINE FIELD git_branch ON work_item TYPE option<string>;
DEFINE FIELD files_touched ON work_item TYPE option<array>;
DEFINE FIELD done_criteria ON work_item TYPE option<array>;
DEFINE FIELD review_stages ON work_item TYPE option<array>;
DEFINE FIELD post_task_hooks ON work_item TYPE array DEFAULT ['type-check', 'lint', 'unit-test', 'format'];
DEFINE FIELD status ON work_item TYPE string DEFAULT 'pending';
DEFINE FIELD created_at ON work_item TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at ON work_item TYPE option<datetime>;
DEFINE INDEX idx_wi_ms ON work_item FIELDS org, milestone, status;
DEFINE INDEX idx_wi_parallel ON work_item FIELDS org, milestone, parallel_group;

-- recurring_initiative: milestones_template contain {title, description}
REMOVE TABLE IF EXISTS recurring_initiative;
DEFINE TABLE recurring_initiative SCHEMALESS;
DEFINE FIELD org ON recurring_initiative TYPE record<org>;
DEFINE FIELD workspace ON recurring_initiative TYPE record<workspace>;
DEFINE FIELD user ON recurring_initiative TYPE record<user>;
DEFINE FIELD title ON recurring_initiative TYPE string;
DEFINE FIELD description ON recurring_initiative TYPE string;
DEFINE FIELD playbook ON recurring_initiative TYPE option<string>;
DEFINE FIELD milestones_template ON recurring_initiative TYPE array DEFAULT [];
DEFINE FIELD variables ON recurring_initiative TYPE option<object>;
DEFINE FIELD cron ON recurring_initiative TYPE string;
DEFINE FIELD last_run ON recurring_initiative TYPE option<datetime>;
DEFINE FIELD next_run ON recurring_initiative TYPE option<datetime>;
DEFINE FIELD enabled ON recurring_initiative TYPE bool DEFAULT true;
DEFINE FIELD created_at ON recurring_initiative TYPE datetime DEFAULT time::now();

-- task: needs discipline, perspective, specialties_loaded, source, engagement fields
-- that were added by executor code but not in the original schema
REMOVE TABLE IF EXISTS task;
DEFINE TABLE task SCHEMALESS;
DEFINE FIELD org ON task TYPE record<org>;
DEFINE FIELD workspace ON task TYPE record<workspace>;
DEFINE FIELD user ON task TYPE record<user>;
DEFINE FIELD description ON task TYPE string;
DEFINE FIELD discipline ON task TYPE option<string>;
DEFINE FIELD domain_path ON task TYPE option<string>;
DEFINE FIELD archetype ON task TYPE option<string>;
DEFINE FIELD mode ON task TYPE option<string>;
DEFINE FIELD perspective ON task TYPE option<string>;
DEFINE FIELD intelligence_loaded ON task TYPE option<object>;
DEFINE FIELD output ON task TYPE option<string>;
DEFINE FIELD model_used ON task TYPE option<string>;
DEFINE FIELD source ON task TYPE option<string>;
DEFINE FIELD status ON task TYPE string DEFAULT 'pending';
DEFINE FIELD cost ON task TYPE option<float>;
DEFINE FIELD skill_used ON task TYPE option<string>;
DEFINE FIELD strategies_used ON task TYPE option<array>;
DEFINE FIELD specialties_loaded ON task TYPE option<array>;
DEFINE FIELD engagement ON task TYPE option<object>;
DEFINE FIELD self_assessment ON task TYPE option<object>;
DEFINE FIELD intelligence_utilization ON task TYPE option<object>;
DEFINE FIELD feedback_score ON task TYPE option<float>;
DEFINE FIELD feedback_human ON task TYPE option<string>;
DEFINE FIELD session_id ON task TYPE option<string>;
DEFINE FIELD calibrated_assessment ON task TYPE option<object>;
-- Allow arbitrary sub-fields in object-typed task columns (SurrealDB v3 SCHEMAFULL)
DEFINE FIELD intelligence_loaded.* ON task TYPE any;
DEFINE FIELD engagement.* ON task TYPE any;
DEFINE FIELD self_assessment.* ON task TYPE any;
DEFINE FIELD intelligence_utilization.* ON task TYPE any;
DEFINE FIELD calibrated_assessment.* ON task TYPE any;
DEFINE FIELD created_at ON task TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at ON task TYPE option<datetime>;
DEFINE INDEX idx_task_org ON task FIELDS org;
DEFINE INDEX idx_task_status ON task FIELDS org, status;

-- specialty: needs status, perspective, bootstrapped, insight_count, min_threshold
-- fields added by specialty_resolver that weren't in original schema
REMOVE TABLE IF EXISTS specialty;
DEFINE TABLE specialty SCHEMALESS;
DEFINE FIELD org ON specialty TYPE record<org>;
DEFINE FIELD slug ON specialty TYPE string;
DEFINE FIELD name ON specialty TYPE string;
DEFINE FIELD description ON specialty TYPE option<string>;
DEFINE FIELD parents ON specialty TYPE array DEFAULT [];
DEFINE FIELD task_count ON specialty TYPE int DEFAULT 0;
DEFINE FIELD health_score ON specialty TYPE float DEFAULT 0;
DEFINE FIELD maturation_phase ON specialty TYPE int DEFAULT 1;
DEFINE FIELD maturation_score ON specialty TYPE int DEFAULT 0;
DEFINE FIELD last_active ON specialty TYPE option<datetime>;
DEFINE FIELD status ON specialty TYPE option<string>;
DEFINE FIELD perspective ON specialty TYPE option<string>;
DEFINE FIELD bootstrapped ON specialty TYPE bool DEFAULT false;
DEFINE FIELD insight_count ON specialty TYPE int DEFAULT 0;
DEFINE FIELD min_threshold ON specialty TYPE int DEFAULT 0;
DEFINE FIELD created_at ON specialty TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_specialty_org ON specialty FIELDS org;
DEFINE INDEX idx_specialty_slug ON specialty FIELDS org, slug UNIQUE;

-- observation: needs source field for test filtering + flexible metadata
REMOVE TABLE IF EXISTS observation;
DEFINE TABLE observation SCHEMALESS;
DEFINE FIELD org ON observation TYPE record<org>;
DEFINE FIELD workspace ON observation TYPE record<workspace>;
DEFINE FIELD observation_type ON observation TYPE string;
DEFINE FIELD content ON observation TYPE string;
DEFINE FIELD domain_hint ON observation TYPE option<string>;
DEFINE FIELD discipline_hint ON observation TYPE option<string>;
DEFINE FIELD confidence ON observation TYPE float DEFAULT 0.5;
DEFINE FIELD source ON observation TYPE option<string>;
DEFINE FIELD source_memory ON observation TYPE option<string>;
DEFINE FIELD source_memories ON observation TYPE option<array>;
DEFINE FIELD session_id ON observation TYPE option<string>;
DEFINE FIELD synthesized ON observation TYPE bool DEFAULT false;
DEFINE FIELD expires_at ON observation TYPE option<datetime>;
DEFINE FIELD created_at ON observation TYPE datetime DEFAULT time::now();

-- Bump schema version
UPDATE config_entry SET value = '34' WHERE key = 'schema_version';
