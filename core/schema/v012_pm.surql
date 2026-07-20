-- v012: Autonomous PM tables
-- Reference: docs/ace-22-work-hierarchy.md (Doc 22)

-- ============================================================
-- INITIATIVE — strategic goal (replaces the old "job" concept)
-- ============================================================
DEFINE TABLE initiative SCHEMAFULL;
DEFINE FIELD org               ON TABLE initiative TYPE record<org>;
DEFINE FIELD workspace         ON TABLE initiative TYPE record<workspace>;
DEFINE FIELD user              ON TABLE initiative TYPE record<user>;
DEFINE FIELD title             ON TABLE initiative TYPE string;
DEFINE FIELD description       ON TABLE initiative TYPE string;
DEFINE FIELD source            ON TABLE initiative TYPE string;
    -- idea | user_created | recurring
DEFINE FIELD source_idea       ON TABLE initiative TYPE option<record<idea>>;
DEFINE FIELD playbook          ON TABLE initiative TYPE option<record<playbook>>;
DEFINE FIELD milestones        ON TABLE initiative TYPE array DEFAULT [];
DEFINE FIELD success_criteria  ON TABLE initiative TYPE option<array>;
DEFINE FIELD owner             ON TABLE initiative TYPE record<user>;
DEFINE FIELD status            ON TABLE initiative TYPE string DEFAULT 'planning';
    -- planning | active | paused | completed | cancelled
DEFINE FIELD priority          ON TABLE initiative TYPE string DEFAULT 'medium';
    -- low | medium | high | critical
DEFINE FIELD total_cost        ON TABLE initiative TYPE float DEFAULT 0.0;
DEFINE FIELD cost_budget       ON TABLE initiative TYPE option<float>;
DEFINE FIELD git_base_branch   ON TABLE initiative TYPE option<string>;
DEFINE FIELD created_at        ON TABLE initiative TYPE datetime DEFAULT time::now();
DEFINE FIELD target_date       ON TABLE initiative TYPE option<datetime>;
DEFINE FIELD completed_at      ON TABLE initiative TYPE option<datetime>;
DEFINE INDEX idx_init_status   ON TABLE initiative FIELDS org, status;

-- ============================================================
-- MILESTONE — measurable checkpoint within an initiative
-- ============================================================
DEFINE TABLE milestone SCHEMAFULL;
DEFINE FIELD org               ON TABLE milestone TYPE record<org>;
DEFINE FIELD initiative        ON TABLE milestone TYPE record<initiative>;
DEFINE FIELD title             ON TABLE milestone TYPE string;
DEFINE FIELD description       ON TABLE milestone TYPE string;
DEFINE FIELD done_criteria     ON TABLE milestone TYPE array DEFAULT [];
DEFINE FIELD work_items        ON TABLE milestone TYPE array DEFAULT [];
DEFINE FIELD depends_on        ON TABLE milestone TYPE option<array>;
DEFINE FIELD sequence          ON TABLE milestone TYPE int;
DEFINE FIELD requires_approval ON TABLE milestone TYPE bool DEFAULT false;
DEFINE FIELD approver          ON TABLE milestone TYPE option<record<user>>;
DEFINE FIELD status            ON TABLE milestone TYPE string DEFAULT 'pending';
    -- pending | active | review | approved | completed | blocked
DEFINE FIELD git_merge_point   ON TABLE milestone TYPE bool DEFAULT true;
DEFINE FIELD created_at        ON TABLE milestone TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at      ON TABLE milestone TYPE option<datetime>;
DEFINE INDEX idx_ms_init       ON TABLE milestone FIELDS org, initiative, sequence;

-- ============================================================
-- WORK_ITEM — concrete deliverable within a milestone
-- ============================================================
DEFINE TABLE work_item SCHEMAFULL;
DEFINE FIELD org               ON TABLE work_item TYPE record<org>;
DEFINE FIELD milestone         ON TABLE work_item TYPE record<milestone>;
DEFINE FIELD initiative        ON TABLE work_item TYPE record<initiative>;
DEFINE FIELD title             ON TABLE work_item TYPE string;
DEFINE FIELD description       ON TABLE work_item TYPE string;
DEFINE FIELD archetype         ON TABLE work_item TYPE string;
DEFINE FIELD mode              ON TABLE work_item TYPE string;
DEFINE FIELD skill             ON TABLE work_item TYPE option<string>;
DEFINE FIELD domain_path       ON TABLE work_item TYPE string;
DEFINE FIELD tasks             ON TABLE work_item TYPE array DEFAULT [];
DEFINE FIELD depends_on        ON TABLE work_item TYPE option<array>;
DEFINE FIELD parallel_group    ON TABLE work_item TYPE option<int>;
DEFINE FIELD assigned_to       ON TABLE work_item TYPE option<record<user>>;
DEFINE FIELD requires_human    ON TABLE work_item TYPE bool DEFAULT false;
DEFINE FIELD handoff_from      ON TABLE work_item TYPE option<record<user>>;
DEFINE FIELD git_branch        ON TABLE work_item TYPE option<string>;
DEFINE FIELD files_touched     ON TABLE work_item TYPE option<array>;
DEFINE FIELD done_criteria     ON TABLE work_item TYPE option<array>;
DEFINE FIELD review_stages     ON TABLE work_item TYPE option<array>;
DEFINE FIELD post_task_hooks   ON TABLE work_item TYPE array DEFAULT ['type-check', 'lint', 'unit-test', 'format'];
DEFINE FIELD status            ON TABLE work_item TYPE string DEFAULT 'pending';
    -- pending | queued | running | review | completed | blocked | failed
DEFINE FIELD created_at        ON TABLE work_item TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at      ON TABLE work_item TYPE option<datetime>;
DEFINE INDEX idx_wi_ms         ON TABLE work_item FIELDS org, milestone, status;
DEFINE INDEX idx_wi_parallel   ON TABLE work_item FIELDS org, milestone, parallel_group;

-- ============================================================
-- RECURRING_INITIATIVE — cron-scheduled initiative template
-- ============================================================
DEFINE TABLE recurring_initiative SCHEMAFULL;
DEFINE FIELD org               ON TABLE recurring_initiative TYPE record<org>;
DEFINE FIELD workspace         ON TABLE recurring_initiative TYPE record<workspace>;
DEFINE FIELD user              ON TABLE recurring_initiative TYPE record<user>;
DEFINE FIELD title             ON TABLE recurring_initiative TYPE string;
DEFINE FIELD description       ON TABLE recurring_initiative TYPE string;
DEFINE FIELD playbook          ON TABLE recurring_initiative TYPE option<string>;
DEFINE FIELD milestones_template ON TABLE recurring_initiative TYPE array DEFAULT [];
DEFINE FIELD variables         ON TABLE recurring_initiative TYPE option<object>;
DEFINE FIELD cron              ON TABLE recurring_initiative TYPE string;
DEFINE FIELD last_run          ON TABLE recurring_initiative TYPE option<datetime>;
DEFINE FIELD next_run          ON TABLE recurring_initiative TYPE option<datetime>;
DEFINE FIELD enabled           ON TABLE recurring_initiative TYPE bool DEFAULT true;
DEFINE FIELD created_at        ON TABLE recurring_initiative TYPE datetime DEFAULT time::now();

-- ============================================================
-- RESOURCE_LOCK — file-level locks with TTL expiry
-- ============================================================
DEFINE TABLE resource_lock SCHEMAFULL;
DEFINE FIELD org               ON TABLE resource_lock TYPE record<org>;
DEFINE FIELD resource_type     ON TABLE resource_lock TYPE string;
    -- file | branch | codebase | document | specialty
DEFINE FIELD resource_id       ON TABLE resource_lock TYPE string;
DEFINE FIELD held_by           ON TABLE resource_lock TYPE string;
    -- work_item ID or task ID
DEFINE FIELD held_since        ON TABLE resource_lock TYPE datetime DEFAULT time::now();
DEFINE FIELD expires_at        ON TABLE resource_lock TYPE datetime;
DEFINE INDEX idx_lock          ON TABLE resource_lock FIELDS org, resource_type, resource_id UNIQUE;

-- ============================================================
-- Add review_confidence_threshold to domain_flow_config
-- ============================================================
DEFINE FIELD review_confidence_threshold ON TABLE domain_flow_config TYPE float DEFAULT 0.80;

-- ============================================================
-- Remove old job and recurring_job tables (replaced by hierarchy)
-- These may not exist yet — REMOVE is idempotent in SurrealDB v3
-- ============================================================
REMOVE TABLE IF EXISTS job;
REMOVE TABLE IF EXISTS recurring_job;

-- Bump schema version
UPSERT config_entry SET key = 'schema_version', value = '12'
    WHERE key = 'schema_version';
