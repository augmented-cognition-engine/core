-- v054: Hierarchy rename — org → product, graph_instance → graph
--
-- Target hierarchy: tenant → product → project → graph
--
-- The Python code rename (org_id → product_id, $org → $product) was applied
-- in a previous migration. This schema migration adds the `product` field to
-- all tables that previously had `org`, populates it from existing org data,
-- and creates the new `product` and `graph` canonical tables.
--
-- Strategy:
--   1. Create `product` table (canonical replacement for `org`)
--   2. Copy all org records to product (org:xyz → product:xyz)
--   3. Add `product` field to ALL tables that had `org`, populate from org
--   4. Create `graph` table (canonical replacement for `graph_instance`)
--   5. Copy graph_instance records to graph
--
-- Note: `org` and `graph_instance` tables are kept (backward compat).
-- A future v055 will drop them once fully migrated.

-- ================================================================
-- 1. DEFINE product TABLE (replaces org)
-- ================================================================
DEFINE TABLE product SCHEMALESS;
DEFINE FIELD name       ON product TYPE string;
DEFINE FIELD tenant     ON product TYPE record<tenant>;
DEFINE FIELD settings   ON product TYPE object DEFAULT {};
DEFINE FIELD created_at ON product TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_product_tenant ON product FIELDS tenant;

-- ================================================================
-- 2. MIGRATE org → product (copy records, transform IDs)
-- ================================================================
FOR $rec IN (SELECT * FROM org) {
    LET $new_id = type::record(string::concat('product:', meta::id($rec.id)));
    UPSERT $new_id SET
        name       = $rec.name,
        tenant     = $rec.tenant,
        settings   = $rec.settings ?? {},
        created_at = $rec.created_at ?? time::now();
};

-- ================================================================
-- 3. ADD product FIELD to all tables + populate from org
--    Structural tables
-- ================================================================
DEFINE FIELD product ON TABLE workspace TYPE option<record<product>>;
UPDATE workspace SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE membership TYPE option<record<product>>;
UPDATE membership SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE domain TYPE option<record<product>>;
UPDATE domain SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE subdomain TYPE option<record<product>>;
UPDATE subdomain SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE specialty TYPE option<record<product>>;
UPDATE specialty SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE domain_flow_config TYPE option<record<product>>;
UPDATE domain_flow_config SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- Hierarchy tables
DEFINE FIELD product ON TABLE ecosystem TYPE option<record<product>>;
UPDATE ecosystem SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE project TYPE option<record<product>>;
UPDATE project SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Intelligence / memory tables (v002)
-- ================================================================
DEFINE FIELD product ON TABLE observation TYPE option<record<product>>;
UPDATE observation SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE insight TYPE option<record<product>>;
UPDATE insight SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE task TYPE option<record<product>>;
UPDATE task SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE memory TYPE option<record<product>>;
UPDATE memory SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE conflict TYPE option<record<product>>;
UPDATE conflict SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Maturation tables (v003)
-- ================================================================
DEFINE FIELD product ON TABLE maturation TYPE option<record<product>>;
UPDATE maturation SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE maturation_history TYPE option<record<product>>;
UPDATE maturation_history SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Document (v004), Synapse (v005)
-- ================================================================
DEFINE FIELD product ON TABLE document TYPE option<record<product>>;
UPDATE document SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE synapse TYPE option<record<product>>;
UPDATE synapse SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Scheduler / signals (v007)
-- ================================================================
DEFINE FIELD product ON TABLE engine_run TYPE option<record<product>>;
UPDATE engine_run SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE output_version TYPE option<record<product>>;
UPDATE output_version SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE research_queue TYPE option<record<product>>;
UPDATE research_queue SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Briefings (v008)
-- ================================================================
DEFINE FIELD product ON TABLE briefing TYPE option<record<product>>;
UPDATE briefing SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Skills (v010)
-- ================================================================
DEFINE FIELD product ON TABLE skill TYPE option<record<product>>;
UPDATE skill SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE skill_execution TYPE option<record<product>>;
UPDATE skill_execution SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Reasoning / frameworks (v011)
-- ================================================================
DEFINE FIELD product ON TABLE framework TYPE option<record<product>>;
UPDATE framework SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE framework_perf TYPE option<record<product>>;
UPDATE framework_perf SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    PM (v012)
-- ================================================================
DEFINE FIELD product ON TABLE initiative TYPE option<record<product>>;
UPDATE initiative SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE milestone TYPE option<record<product>>;
UPDATE milestone SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE work_item TYPE option<record<product>>;
UPDATE work_item SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE recurring_initiative TYPE option<record<product>>;
UPDATE recurring_initiative SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE resource_lock TYPE option<record<product>>;
UPDATE resource_lock SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Ideas / Playbooks (v013)
-- ================================================================
DEFINE FIELD product ON TABLE idea TYPE option<record<product>>;
UPDATE idea SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE playbook TYPE option<record<product>>;
UPDATE playbook SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Portal / Chat (v014)
-- ================================================================
DEFINE FIELD product ON TABLE chat_session TYPE option<record<product>>;
UPDATE chat_session SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE notification TYPE option<record<product>>;
UPDATE notification SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE notification_pref TYPE option<record<product>>;
UPDATE notification_pref SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE document_version TYPE option<record<product>>;
UPDATE document_version SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Advanced intelligence (v015)
-- ================================================================
DEFINE FIELD product ON TABLE experiment_log TYPE option<record<product>>;
UPDATE experiment_log SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE calibration TYPE option<record<product>>;
UPDATE calibration SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE roi_event TYPE option<record<product>>;
UPDATE roi_event SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Templates (v019)
-- ================================================================
DEFINE FIELD product ON TABLE template TYPE option<record<product>>;
UPDATE template SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Measurement (v020)
-- ================================================================
DEFINE FIELD product ON TABLE daily_metrics TYPE option<record<product>>;
UPDATE daily_metrics SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE calibration_snapshot TYPE option<record<product>>;
UPDATE calibration_snapshot SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Evolution (v021)
-- ================================================================
DEFINE FIELD product ON TABLE evolution_run TYPE option<record<product>>;
UPDATE evolution_run SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE source_reputation TYPE option<record<product>>;
UPDATE source_reputation SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE autonomy_level TYPE option<record<product>>;
UPDATE autonomy_level SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Orchestration (v023)
-- ================================================================
DEFINE FIELD product ON TABLE orchestration_run TYPE option<record<product>>;
UPDATE orchestration_run SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE orchestration_event TYPE option<record<product>>;
UPDATE orchestration_event SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Self-optimizer (v027)
-- ================================================================
DEFINE FIELD product ON TABLE self_optimizer_state TYPE option<record<product>>;
UPDATE self_optimizer_state SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE self_optimizer_proposal TYPE option<record<product>>;
UPDATE self_optimizer_proposal SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE specialty_affinity TYPE option<record<product>>;
UPDATE specialty_affinity SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Product awareness (v032)
-- ================================================================
DEFINE FIELD product ON TABLE capability TYPE option<record<product>>;
UPDATE capability SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE active_discipline TYPE option<record<product>>;
UPDATE active_discipline SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE agent_spec TYPE option<record<product>>;
UPDATE agent_spec SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE agent_feedback TYPE option<record<product>>;
UPDATE agent_feedback SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE capability_scan TYPE option<record<product>>;
UPDATE capability_scan SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE capability_quality TYPE option<record<product>>;
UPDATE capability_quality SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Vision / Themes (v036)
-- ================================================================
DEFINE FIELD product ON TABLE theme TYPE option<record<product>>;
UPDATE theme SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    ATC / Live (v037)
-- ================================================================
DEFINE FIELD product ON TABLE agent_session TYPE option<record<product>>;
UPDATE agent_session SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE active_edit TYPE option<record<product>>;
UPDATE active_edit SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE agent_execution TYPE option<record<product>>;
UPDATE agent_execution SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Connected graph / decisions (v040)
-- ================================================================
DEFINE FIELD product ON TABLE decision TYPE option<record<product>>;
UPDATE decision SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Agent config (v042)
-- ================================================================
DEFINE FIELD product ON TABLE agent_config_override TYPE option<record<product>>;
UPDATE agent_config_override SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Composition / Token (v043)
-- ================================================================
DEFINE FIELD product ON TABLE composition_signal TYPE option<record<product>>;
UPDATE composition_signal SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE token_baseline TYPE option<record<product>>;
UPDATE token_baseline SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    ATC Flight (v045)
-- ================================================================
DEFINE FIELD product ON TABLE atc_flight TYPE option<record<product>>;
UPDATE atc_flight SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Verification (v046)
-- ================================================================
DEFINE FIELD product ON TABLE verification_evidence TYPE option<record<product>>;
UPDATE verification_evidence SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE verification_signal TYPE option<record<product>>;
UPDATE verification_signal SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE evaluator_judgment TYPE option<record<product>>;
UPDATE evaluator_judgment SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE simplicity_audit TYPE option<record<product>>;
UPDATE simplicity_audit SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Engine schedule (v050), session digest (v051)
-- ================================================================
DEFINE FIELD product ON TABLE engine_schedule_override TYPE option<record<product>>;
UPDATE engine_schedule_override SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE session_digest TYPE option<record<product>>;
UPDATE session_digest SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
--    Capability lifecycle (v052)
-- ================================================================
DEFINE FIELD product ON TABLE capability_lifecycle_track TYPE option<record<product>>;
UPDATE capability_lifecycle_track SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE conductor_rule TYPE option<record<product>>;
UPDATE conductor_rule SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE conductor_rule_execution TYPE option<record<product>>;
UPDATE conductor_rule_execution SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

DEFINE FIELD product ON TABLE quality_template TYPE option<record<product>>;
UPDATE quality_template SET product = type::record(string::concat('product:', meta::id(org))) WHERE org IS NOT NULL;

-- ================================================================
-- 4. DEFINE graph TABLE (replaces graph_instance)
-- ================================================================
DEFINE TABLE graph SCHEMALESS;
DEFINE FIELD project ON TABLE graph TYPE option<record<project>>;

-- ================================================================
-- 5. MIGRATE graph_instance → graph
-- ================================================================
FOR $rec IN (SELECT * FROM graph_instance) {
    LET $new_id = type::record(string::concat('graph:', meta::id($rec.id)));
    UPSERT $new_id SET
        graph_id   = $rec.graph_id,
        name       = $rec.name ?? $rec.graph_id,
        repo_path  = $rec.repo_path,
        mode       = $rec.mode ?? 'permanent',
        node_count = $rec.node_count ?? 0,
        scanned_at = $rec.scanned_at ?? time::now();
};

-- ================================================================
-- 6. BUMP schema version
-- ================================================================
UPDATE config_entry SET value = '54' WHERE key = 'schema_version';
