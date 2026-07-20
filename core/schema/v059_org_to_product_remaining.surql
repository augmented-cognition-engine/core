-- v059: Fix remaining 60 tables where org field was still typed record<org>.
--
-- v058 caught the first batch of tables but missed these. Any write passing
-- product:platform (or any product:* record) was silently rejected by SurrealDB
-- because record<org> validates the table name strictly.
--
-- Discovered via: ace_capture returning empty id despite status='captured'.
-- Root cause: observation.org = record<org> rejected product:platform writes.
--
-- Applied live on 2026-04-05. This migration makes the fix permanent in schema.

REMOVE FIELD org ON active_discipline;
DEFINE FIELD org ON active_discipline TYPE record<product>;

REMOVE FIELD org ON active_edit;
DEFINE FIELD org ON active_edit TYPE record<product>;

REMOVE FIELD org ON agent_execution;
DEFINE FIELD org ON agent_execution TYPE record<product>;

REMOVE FIELD org ON agent_session;
DEFINE FIELD org ON agent_session TYPE record<product>;

REMOVE FIELD org ON autonomy_level;
DEFINE FIELD org ON autonomy_level TYPE record<product>;

REMOVE FIELD org ON briefing;
DEFINE FIELD org ON briefing TYPE record<product>;

REMOVE FIELD org ON calibration;
DEFINE FIELD org ON calibration TYPE record<product>;

REMOVE FIELD org ON calibration_snapshot;
DEFINE FIELD org ON calibration_snapshot TYPE record<product>;

REMOVE FIELD org ON capability;
DEFINE FIELD org ON capability TYPE record<product>;

REMOVE FIELD org ON capability_quality;
DEFINE FIELD org ON capability_quality TYPE record<product>;

REMOVE FIELD org ON capability_scan;
DEFINE FIELD org ON capability_scan TYPE record<product>;

REMOVE FIELD org ON chat_session;
DEFINE FIELD org ON chat_session TYPE record<product>;

REMOVE FIELD org ON conflict;
DEFINE FIELD org ON conflict TYPE record<product>;

REMOVE FIELD org ON daily_metrics;
DEFINE FIELD org ON daily_metrics TYPE record<product>;

REMOVE FIELD org ON document;
DEFINE FIELD org ON document TYPE record<product>;

REMOVE FIELD org ON document_version;
DEFINE FIELD org ON document_version TYPE record<product>;

REMOVE FIELD org ON domain;
DEFINE FIELD org ON domain TYPE record<product>;

REMOVE FIELD org ON domain_flow_config;
DEFINE FIELD org ON domain_flow_config TYPE record<product>;

REMOVE FIELD org ON ecosystem;
DEFINE FIELD org ON ecosystem TYPE record<product>;

REMOVE FIELD org ON engine_run;
DEFINE FIELD org ON engine_run TYPE record<product>;

REMOVE FIELD org ON evolution_run;
DEFINE FIELD org ON evolution_run TYPE record<product>;

REMOVE FIELD org ON experiment_log;
DEFINE FIELD org ON experiment_log TYPE record<product>;

REMOVE FIELD org ON framework;
DEFINE FIELD org ON framework TYPE record<product>;

REMOVE FIELD org ON framework_perf;
DEFINE FIELD org ON framework_perf TYPE record<product>;

REMOVE FIELD org ON idea;
DEFINE FIELD org ON idea TYPE record<product>;

REMOVE FIELD org ON initiative;
DEFINE FIELD org ON initiative TYPE record<product>;

REMOVE FIELD org ON insight;
DEFINE FIELD org ON insight TYPE record<product>;

REMOVE FIELD org ON maturation;
DEFINE FIELD org ON maturation TYPE record<product>;

REMOVE FIELD org ON maturation_history;
DEFINE FIELD org ON maturation_history TYPE record<product>;

REMOVE FIELD org ON membership;
DEFINE FIELD org ON membership TYPE record<product>;

REMOVE FIELD org ON memory;
DEFINE FIELD org ON memory TYPE record<product>;

REMOVE FIELD org ON milestone;
DEFINE FIELD org ON milestone TYPE record<product>;

REMOVE FIELD org ON notification;
DEFINE FIELD org ON notification TYPE record<product>;

REMOVE FIELD org ON notification_pref;
DEFINE FIELD org ON notification_pref TYPE record<product>;

REMOVE FIELD org ON observation;
DEFINE FIELD org ON observation TYPE record<product>;

REMOVE FIELD org ON orchestration_event;
DEFINE FIELD org ON orchestration_event TYPE record<product>;

REMOVE FIELD org ON orchestration_run;
DEFINE FIELD org ON orchestration_run TYPE record<product>;

REMOVE FIELD org ON output_version;
DEFINE FIELD org ON output_version TYPE record<product>;

REMOVE FIELD org ON playbook;
DEFINE FIELD org ON playbook TYPE record<product>;

REMOVE FIELD org ON product_answer;
DEFINE FIELD org ON product_answer TYPE record<product>;

REMOVE FIELD org ON product_question;
DEFINE FIELD org ON product_question TYPE record<product>;

REMOVE FIELD org ON product_vision;
DEFINE FIELD org ON product_vision TYPE record<product>;

REMOVE FIELD org ON project;
DEFINE FIELD org ON project TYPE record<product>;

REMOVE FIELD org ON recurring_initiative;
DEFINE FIELD org ON recurring_initiative TYPE record<product>;

REMOVE FIELD org ON research_queue;
DEFINE FIELD org ON research_queue TYPE record<product>;

REMOVE FIELD org ON roi_event;
DEFINE FIELD org ON roi_event TYPE record<product>;

REMOVE FIELD org ON self_optimizer_proposal;
DEFINE FIELD org ON self_optimizer_proposal TYPE record<product>;

REMOVE FIELD org ON self_optimizer_state;
DEFINE FIELD org ON self_optimizer_state TYPE record<product>;

REMOVE FIELD org ON skill;
DEFINE FIELD org ON skill TYPE record<product>;

REMOVE FIELD org ON skill_execution;
DEFINE FIELD org ON skill_execution TYPE record<product>;

REMOVE FIELD org ON source_reputation;
DEFINE FIELD org ON source_reputation TYPE record<product>;

REMOVE FIELD org ON specialty;
DEFINE FIELD org ON specialty TYPE record<product>;

REMOVE FIELD org ON specialty_affinity;
DEFINE FIELD org ON specialty_affinity TYPE record<product>;

REMOVE FIELD org ON subdomain;
DEFINE FIELD org ON subdomain TYPE record<product>;

REMOVE FIELD org ON synapse;
DEFINE FIELD org ON synapse TYPE record<product>;

REMOVE FIELD org ON task;
DEFINE FIELD org ON task TYPE record<product>;

REMOVE FIELD org ON template;
DEFINE FIELD org ON template TYPE record<product>;

REMOVE FIELD org ON theme;
DEFINE FIELD org ON theme TYPE record<product>;

REMOVE FIELD org ON work_item;
DEFINE FIELD org ON work_item TYPE record<product>;

REMOVE FIELD org ON workspace;
DEFINE FIELD org ON workspace TYPE record<product>;

UPDATE config_entry SET value = '59' WHERE key = 'schema_version';
