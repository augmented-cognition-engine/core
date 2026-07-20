-- v061: Remove org and workspace fields. Use product as the single root field.
--
-- Background:
--   - schema v058 renamed the org TABLE to product, changing record IDs from
--     org:* to product:*. Code continued writing "org = <record>$product"
--     alongside the new "product = <record>$product" as a dual-write.
--   - workspace was an early concept (developer context) that was never used.
--   - We have one product (product:platform) and tenant=default.
--   - All code writes have been updated to use product only (see v061 code PR).
--
-- This migration:
--   1. Backfills product = product:platform for any rows that still have product IS NONE
--   2. Removes the workspace field from initiative and recurring_initiative
--   3. Removes the org field definition from all tables (data will be unset too)

-- ─── Step 1: Backfill product field ──────────────────────────────────────────
-- Single product setup: all records belong to product:platform.
-- Rows that have org set but product unset get product = org (which is now product:platform).
-- Rows with no org and no product also get product:platform (our only product).

UPDATE active_discipline   SET product = product:platform WHERE product IS NONE;
UPDATE active_edit         SET product = product:platform WHERE product IS NONE;
UPDATE agent_execution     SET product = product:platform WHERE product IS NONE;
UPDATE agent_session       SET product = product:platform WHERE product IS NONE;
UPDATE autonomy_level      SET product = product:platform WHERE product IS NONE;
UPDATE briefing            SET product = product:platform WHERE product IS NONE;
UPDATE calibration         SET product = product:platform WHERE product IS NONE;
UPDATE calibration_snapshot SET product = product:platform WHERE product IS NONE;
UPDATE capability          SET product = product:platform WHERE product IS NONE;
UPDATE capability_quality  SET product = product:platform WHERE product IS NONE;
UPDATE capability_scan     SET product = product:platform WHERE product IS NONE;
UPDATE chat_session        SET product = product:platform WHERE product IS NONE;
UPDATE conflict            SET product = product:platform WHERE product IS NONE;
UPDATE daily_metrics       SET product = product:platform WHERE product IS NONE;
UPDATE decision            SET product = product:platform WHERE product IS NONE;
UPDATE document            SET product = product:platform WHERE product IS NONE;
UPDATE document_version    SET product = product:platform WHERE product IS NONE;
UPDATE domain              SET product = product:platform WHERE product IS NONE;
UPDATE domain_flow_config  SET product = product:platform WHERE product IS NONE;
UPDATE ecosystem           SET product = product:platform WHERE product IS NONE;
UPDATE engine_run          SET product = product:platform WHERE product IS NONE;
UPDATE evolution_run       SET product = product:platform WHERE product IS NONE;
UPDATE experiment_log      SET product = product:platform WHERE product IS NONE;
UPDATE framework           SET product = product:platform WHERE product IS NONE;
UPDATE framework_perf      SET product = product:platform WHERE product IS NONE;
UPDATE idea                SET product = product:platform WHERE product IS NONE;
UPDATE initiative          SET product = product:platform WHERE product IS NONE;
UPDATE insight             SET product = product:platform WHERE product IS NONE;
UPDATE maturation          SET product = product:platform WHERE product IS NONE;
UPDATE maturation_history  SET product = product:platform WHERE product IS NONE;
UPDATE membership          SET product = product:platform WHERE product IS NONE;
UPDATE memory              SET product = product:platform WHERE product IS NONE;
UPDATE milestone           SET product = product:platform WHERE product IS NONE;
UPDATE notification        SET product = product:platform WHERE product IS NONE;
UPDATE notification_pref   SET product = product:platform WHERE product IS NONE;
UPDATE observation         SET product = product:platform WHERE product IS NONE;
UPDATE orchestration_event SET product = product:platform WHERE product IS NONE;
UPDATE orchestration_run   SET product = product:platform WHERE product IS NONE;
UPDATE output_version      SET product = product:platform WHERE product IS NONE;
UPDATE playbook            SET product = product:platform WHERE product IS NONE;
UPDATE product_answer      SET product = product:platform WHERE product IS NONE;
UPDATE product_question    SET product = product:platform WHERE product IS NONE;
UPDATE product_vision      SET product = product:platform WHERE product IS NONE;
UPDATE project             SET product = product:platform WHERE product IS NONE;
UPDATE recurring_initiative SET product = product:platform WHERE product IS NONE;
UPDATE research_queue      SET product = product:platform WHERE product IS NONE;
UPDATE roi_event           SET product = product:platform WHERE product IS NONE;
UPDATE self_optimizer_proposal SET product = product:platform WHERE product IS NONE;
UPDATE self_optimizer_state SET product = product:platform WHERE product IS NONE;
UPDATE skill               SET product = product:platform WHERE product IS NONE;
UPDATE skill_execution     SET product = product:platform WHERE product IS NONE;
UPDATE source_reputation   SET product = product:platform WHERE product IS NONE;
UPDATE specialty           SET product = product:platform WHERE product IS NONE;
UPDATE specialty_affinity  SET product = product:platform WHERE product IS NONE;
UPDATE subdomain           SET product = product:platform WHERE product IS NONE;
UPDATE synapse             SET product = product:platform WHERE product IS NONE;
UPDATE task                SET product = product:platform WHERE product IS NONE;
UPDATE template            SET product = product:platform WHERE product IS NONE;
UPDATE theme               SET product = product:platform WHERE product IS NONE;
UPDATE work_item           SET product = product:platform WHERE product IS NONE;
UPDATE workspace           SET product = product:platform WHERE product IS NONE;

-- ─── Step 2: Remove workspace field from initiative tables ────────────────────

REMOVE FIELD workspace ON TABLE initiative;
UPDATE initiative UNSET workspace;

REMOVE FIELD workspace ON TABLE recurring_initiative;
UPDATE recurring_initiative UNSET workspace;

-- ─── Step 3: Remove org field from all tables ─────────────────────────────────
-- Code no longer writes org. Data is unset so SCHEMALESS tables are also clean.

REMOVE FIELD org ON TABLE active_discipline;   UPDATE active_discipline UNSET org;
REMOVE FIELD org ON TABLE active_edit;         UPDATE active_edit UNSET org;
REMOVE FIELD org ON TABLE agent_execution;     UPDATE agent_execution UNSET org;
REMOVE FIELD org ON TABLE agent_session;       UPDATE agent_session UNSET org;
REMOVE FIELD org ON TABLE autonomy_level;      UPDATE autonomy_level UNSET org;
REMOVE FIELD org ON TABLE briefing;            UPDATE briefing UNSET org;
REMOVE FIELD org ON TABLE calibration;         UPDATE calibration UNSET org;
REMOVE FIELD org ON TABLE calibration_snapshot; UPDATE calibration_snapshot UNSET org;
REMOVE FIELD org ON TABLE capability;          UPDATE capability UNSET org;
REMOVE FIELD org ON TABLE capability_quality;  UPDATE capability_quality UNSET org;
REMOVE FIELD org ON TABLE capability_scan;     UPDATE capability_scan UNSET org;
REMOVE FIELD org ON TABLE chat_session;        UPDATE chat_session UNSET org;
REMOVE FIELD org ON TABLE conflict;            UPDATE conflict UNSET org;
REMOVE FIELD org ON TABLE daily_metrics;       UPDATE daily_metrics UNSET org;
REMOVE FIELD org ON TABLE decision;            UPDATE decision UNSET org;
REMOVE FIELD org ON TABLE document;            UPDATE document UNSET org;
REMOVE FIELD org ON TABLE document_version;    UPDATE document_version UNSET org;
REMOVE FIELD org ON TABLE domain;              UPDATE domain UNSET org;
REMOVE FIELD org ON TABLE domain_flow_config;  UPDATE domain_flow_config UNSET org;
REMOVE FIELD org ON TABLE ecosystem;           UPDATE ecosystem UNSET org;
REMOVE FIELD org ON TABLE engine_run;          UPDATE engine_run UNSET org;
REMOVE FIELD org ON TABLE evolution_run;       UPDATE evolution_run UNSET org;
REMOVE FIELD org ON TABLE experiment_log;      UPDATE experiment_log UNSET org;
REMOVE FIELD org ON TABLE framework;           UPDATE framework UNSET org;
REMOVE FIELD org ON TABLE framework_perf;      UPDATE framework_perf UNSET org;
REMOVE FIELD org ON TABLE idea;                UPDATE idea UNSET org;
REMOVE FIELD org ON TABLE initiative;          UPDATE initiative UNSET org;
REMOVE FIELD org ON TABLE insight;             UPDATE insight UNSET org;
REMOVE FIELD org ON TABLE maturation;          UPDATE maturation UNSET org;
REMOVE FIELD org ON TABLE maturation_history;  UPDATE maturation_history UNSET org;
REMOVE FIELD org ON TABLE membership;          UPDATE membership UNSET org;
REMOVE FIELD org ON TABLE memory;              UPDATE memory UNSET org;
REMOVE FIELD org ON TABLE milestone;           UPDATE milestone UNSET org;
REMOVE FIELD org ON TABLE notification;        UPDATE notification UNSET org;
REMOVE FIELD org ON TABLE notification_pref;   UPDATE notification_pref UNSET org;
REMOVE FIELD org ON TABLE observation;         UPDATE observation UNSET org;
REMOVE FIELD org ON TABLE orchestration_event; UPDATE orchestration_event UNSET org;
REMOVE FIELD org ON TABLE orchestration_run;   UPDATE orchestration_run UNSET org;
REMOVE FIELD org ON TABLE output_version;      UPDATE output_version UNSET org;
REMOVE FIELD org ON TABLE playbook;            UPDATE playbook UNSET org;
REMOVE FIELD org ON TABLE product_answer;      UPDATE product_answer UNSET org;
REMOVE FIELD org ON TABLE product_question;    UPDATE product_question UNSET org;
REMOVE FIELD org ON TABLE product_vision;      UPDATE product_vision UNSET org;
REMOVE FIELD org ON TABLE project;             UPDATE project UNSET org;
REMOVE FIELD org ON TABLE recurring_initiative; UPDATE recurring_initiative UNSET org;
REMOVE FIELD org ON TABLE research_queue;      UPDATE research_queue UNSET org;
REMOVE FIELD org ON TABLE roi_event;           UPDATE roi_event UNSET org;
REMOVE FIELD org ON TABLE self_optimizer_proposal; UPDATE self_optimizer_proposal UNSET org;
REMOVE FIELD org ON TABLE self_optimizer_state; UPDATE self_optimizer_state UNSET org;
REMOVE FIELD org ON TABLE skill;               UPDATE skill UNSET org;
REMOVE FIELD org ON TABLE skill_execution;     UPDATE skill_execution UNSET org;
REMOVE FIELD org ON TABLE source_reputation;   UPDATE source_reputation UNSET org;
REMOVE FIELD org ON TABLE specialty;           UPDATE specialty UNSET org;
REMOVE FIELD org ON TABLE specialty_affinity;  UPDATE specialty_affinity UNSET org;
REMOVE FIELD org ON TABLE subdomain;           UPDATE subdomain UNSET org;
REMOVE FIELD org ON TABLE synapse;             UPDATE synapse UNSET org;
REMOVE FIELD org ON TABLE task;                UPDATE task UNSET org;
REMOVE FIELD org ON TABLE template;            UPDATE template UNSET org;
REMOVE FIELD org ON TABLE theme;               UPDATE theme UNSET org;
REMOVE FIELD org ON TABLE work_item;           UPDATE work_item UNSET org;
REMOVE FIELD org ON TABLE workspace;           UPDATE workspace UNSET org;

-- ─── Step 4: Make product field required on key tables ────────────────────────

REMOVE FIELD product ON TABLE insight;
DEFINE FIELD product ON TABLE insight TYPE record<product>;

REMOVE FIELD product ON TABLE observation;
DEFINE FIELD product ON TABLE observation TYPE record<product>;

REMOVE FIELD product ON TABLE decision;
DEFINE FIELD product ON TABLE decision TYPE record<product>;

REMOVE FIELD product ON TABLE capability;
DEFINE FIELD product ON TABLE capability TYPE record<product>;

REMOVE FIELD product ON TABLE initiative;
DEFINE FIELD product ON TABLE initiative TYPE record<product>;

REMOVE FIELD product ON TABLE specialty;
DEFINE FIELD product ON TABLE specialty TYPE record<product>;

-- ─── Version bump ─────────────────────────────────────────────────────────────
UPDATE config_entry SET value = '61' WHERE key = 'schema_version';
