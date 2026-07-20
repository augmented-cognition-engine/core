-- schema/v019_jobs_templates.surql
-- v019: step→job with frameworks, playbook→template

-- 1. Add jobs field to skill table with frameworks support
DEFINE FIELD jobs ON skill TYPE option<array>;
DEFINE FIELD jobs.* ON skill TYPE object;
DEFINE FIELD jobs.*.name ON skill TYPE string;
DEFINE FIELD jobs.*.archetype ON skill TYPE string;
DEFINE FIELD jobs.*.mode ON skill TYPE string;
DEFINE FIELD jobs.*.frameworks ON skill TYPE option<array>;
DEFINE FIELD jobs.*.frameworks.* ON skill TYPE string;
DEFINE FIELD jobs.*.output_format ON skill TYPE option<string>;
DEFINE FIELD jobs.*.description ON skill TYPE option<string>;

-- Data migration: copy steps → jobs
UPDATE skill SET jobs = steps;

-- 2. Update skill_execution fields (step→job)
DEFINE FIELD jobs_completed ON skill_execution TYPE option<int>;
DEFINE FIELD job_results ON skill_execution TYPE option<array>;
UPDATE skill_execution SET jobs_completed = steps_completed, job_results = step_results;

-- 3. Create template table (replaces old playbook table for initiative templates)
DEFINE TABLE template SCHEMAFULL;
DEFINE FIELD org ON template TYPE record<org>;
DEFINE FIELD name ON template TYPE string;
DEFINE FIELD description ON template TYPE option<string>;
DEFINE FIELD domain_path ON template TYPE option<string>;
DEFINE FIELD milestones ON template TYPE array;
DEFINE FIELD variables ON template TYPE option<array>;
DEFINE FIELD source_initiatives ON template TYPE option<array>;
DEFINE FIELD created_by ON template TYPE option<record<user>>;
DEFINE FIELD times_used ON template TYPE option<int> DEFAULT 0;
DEFINE FIELD avg_feedback ON template TYPE option<float>;
DEFINE FIELD created_at ON template TYPE option<datetime> DEFAULT time::now();
DEFINE FIELD updated_at ON template TYPE option<datetime> DEFAULT time::now();
DEFINE INDEX idx_template_org ON template FIELDS org;

-- Data migration: copy playbook → template
INSERT INTO template (SELECT * FROM playbook);

-- 4. Update initiative foreign keys
DEFINE FIELD template ON initiative TYPE option<record<template>>;
UPDATE initiative SET template = playbook WHERE playbook IS NOT NONE;

DEFINE FIELD template ON recurring_initiative TYPE option<record<template>>;
UPDATE recurring_initiative SET template = playbook WHERE playbook IS NOT NONE;

-- 5. Update source field
UPDATE initiative SET source = 'template' WHERE source = 'playbook';

-- 6. Schema version
UPDATE config_entry SET value = '19' WHERE key = 'schema_version';
