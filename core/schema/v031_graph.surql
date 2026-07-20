-- v031_graph.surql
-- Unified intelligence graph: 12 node types + 15 edge types
-- This is the new graph schema that lives alongside existing tables.
-- Code scanner and new features write here. Existing code untouched.

-- ================================================================
-- CODE NODES
-- ================================================================

DEFINE TABLE graph_file SCHEMAFULL;
DEFINE FIELD path              ON TABLE graph_file TYPE string;
DEFINE FIELD name              ON TABLE graph_file TYPE string;
DEFINE FIELD extension         ON TABLE graph_file TYPE string DEFAULT '';
DEFINE FIELD language          ON TABLE graph_file TYPE string DEFAULT '';
DEFINE FIELD size_bytes        ON TABLE graph_file TYPE int DEFAULT 0;
DEFINE FIELD line_count        ON TABLE graph_file TYPE int DEFAULT 0;
DEFINE FIELD change_frequency  ON TABLE graph_file TYPE int DEFAULT 0;
DEFINE FIELD last_modified     ON TABLE graph_file TYPE option<datetime>;
DEFINE FIELD first_seen        ON TABLE graph_file TYPE datetime DEFAULT time::now();
DEFINE FIELD fragility_score   ON TABLE graph_file TYPE float DEFAULT 0.0;
DEFINE FIELD ownership         ON TABLE graph_file TYPE option<string>;
DEFINE FIELD graph_id          ON TABLE graph_file TYPE string DEFAULT 'default';
DEFINE INDEX idx_gf_path       ON TABLE graph_file FIELDS path, graph_id UNIQUE;
DEFINE INDEX idx_gf_graph      ON TABLE graph_file FIELDS graph_id;
DEFINE INDEX idx_gf_lang       ON TABLE graph_file FIELDS language, graph_id;

DEFINE TABLE graph_function SCHEMAFULL;
DEFINE FIELD name              ON TABLE graph_function TYPE string;
DEFINE FIELD file              ON TABLE graph_function TYPE record<graph_file>;
DEFINE FIELD line_start        ON TABLE graph_function TYPE int DEFAULT 0;
DEFINE FIELD line_end          ON TABLE graph_function TYPE int DEFAULT 0;
DEFINE FIELD kind              ON TABLE graph_function TYPE string DEFAULT 'function';
    -- function | class | method
DEFINE FIELD parameters        ON TABLE graph_function TYPE option<string>;
DEFINE FIELD return_type       ON TABLE graph_function TYPE option<string>;
DEFINE FIELD complexity        ON TABLE graph_function TYPE int DEFAULT 0;
DEFINE FIELD graph_id          ON TABLE graph_function TYPE string DEFAULT 'default';
DEFINE INDEX idx_gfn_name      ON TABLE graph_function FIELDS name, file, graph_id;
DEFINE INDEX idx_gfn_graph     ON TABLE graph_function FIELDS graph_id;

-- ================================================================
-- KNOWLEDGE NODES
-- ================================================================

DEFINE TABLE graph_decision SCHEMAFULL;
DEFINE FIELD title             ON TABLE graph_decision TYPE string;
DEFINE FIELD description       ON TABLE graph_decision TYPE string DEFAULT '';
DEFINE FIELD outcome           ON TABLE graph_decision TYPE string DEFAULT 'unknown';
    -- worked | failed | reverted | unknown
DEFINE FIELD alternatives      ON TABLE graph_decision TYPE array<string> DEFAULT [];
DEFINE FIELD source_commit     ON TABLE graph_decision TYPE option<string>;
DEFINE FIELD source_pr         ON TABLE graph_decision TYPE option<string>;
DEFINE FIELD timestamp         ON TABLE graph_decision TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE graph_decision TYPE float DEFAULT 0.7;
DEFINE FIELD tags              ON TABLE graph_decision TYPE array<string> DEFAULT [];
DEFINE FIELD graph_id          ON TABLE graph_decision TYPE string DEFAULT 'default';
DEFINE INDEX idx_gd_graph      ON TABLE graph_decision FIELDS graph_id;
DEFINE INDEX idx_gd_time       ON TABLE graph_decision FIELDS timestamp, graph_id;

DEFINE TABLE graph_insight SCHEMAFULL;
DEFINE FIELD content           ON TABLE graph_insight TYPE string;
DEFINE FIELD insight_type      ON TABLE graph_insight TYPE string DEFAULT 'fact';
    -- solution | problem | error | fix | code_pattern | dependency | architecture_decision | breaking_change | migration | deprecation | fact | pattern | convention
DEFINE FIELD confidence        ON TABLE graph_insight TYPE float DEFAULT 0.7;
DEFINE FIELD source            ON TABLE graph_insight TYPE string DEFAULT 'capture';
    -- capture | scanner | agent | overnight | user
DEFINE FIELD tags              ON TABLE graph_insight TYPE array<string> DEFAULT [];
DEFINE FIELD status            ON TABLE graph_insight TYPE string DEFAULT 'active';
DEFINE FIELD created_at        ON TABLE graph_insight TYPE datetime DEFAULT time::now();
DEFINE FIELD last_confirmed    ON TABLE graph_insight TYPE datetime DEFAULT time::now();
DEFINE FIELD graph_id          ON TABLE graph_insight TYPE string DEFAULT 'default';
DEFINE INDEX idx_gi_graph      ON TABLE graph_insight FIELDS graph_id, status;
DEFINE INDEX idx_gi_type       ON TABLE graph_insight FIELDS insight_type, graph_id;

-- ================================================================
-- WORK NODES
-- ================================================================

DEFINE TABLE graph_task SCHEMAFULL;
DEFINE FIELD description       ON TABLE graph_task TYPE string;
DEFINE FIELD status            ON TABLE graph_task TYPE string DEFAULT 'pending';
    -- pending | running | completed | failed
DEFINE FIELD output            ON TABLE graph_task TYPE option<string>;
DEFINE FIELD feedback           ON TABLE graph_task TYPE option<string>;
    -- accepted | edited | rejected
DEFINE FIELD agent_config      ON TABLE graph_task TYPE option<object>;
DEFINE FIELD cost              ON TABLE graph_task TYPE float DEFAULT 0.0;
DEFINE FIELD created_at        ON TABLE graph_task TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at      ON TABLE graph_task TYPE option<datetime>;
DEFINE FIELD graph_id          ON TABLE graph_task TYPE string DEFAULT 'default';
DEFINE INDEX idx_gt_graph      ON TABLE graph_task FIELDS graph_id, status;

DEFINE TABLE graph_initiative SCHEMAFULL;
DEFINE FIELD title             ON TABLE graph_initiative TYPE string;
DEFINE FIELD description       ON TABLE graph_initiative TYPE string DEFAULT '';
DEFINE FIELD project           ON TABLE graph_initiative TYPE option<string>;
DEFINE FIELD status            ON TABLE graph_initiative TYPE string DEFAULT 'draft';
    -- draft | active | paused | completed | cancelled
DEFINE FIELD priority          ON TABLE graph_initiative TYPE int DEFAULT 50;
DEFINE FIELD created_at        ON TABLE graph_initiative TYPE datetime DEFAULT time::now();
DEFINE FIELD target_date       ON TABLE graph_initiative TYPE option<datetime>;
DEFINE FIELD graph_id          ON TABLE graph_initiative TYPE string DEFAULT 'default';
DEFINE INDEX idx_ginit_graph   ON TABLE graph_initiative FIELDS graph_id, status;

DEFINE TABLE graph_idea SCHEMAFULL;
DEFINE FIELD title             ON TABLE graph_idea TYPE string;
DEFINE FIELD raw_input         ON TABLE graph_idea TYPE string DEFAULT '';
DEFINE FIELD status            ON TABLE graph_idea TYPE string DEFAULT 'captured';
DEFINE FIELD classification    ON TABLE graph_idea TYPE option<object>;
DEFINE FIELD created_at        ON TABLE graph_idea TYPE datetime DEFAULT time::now();
DEFINE FIELD graph_id          ON TABLE graph_idea TYPE string DEFAULT 'default';
DEFINE INDEX idx_gidea_graph   ON TABLE graph_idea FIELDS graph_id, status;

-- ================================================================
-- CAPABILITY NODES
-- ================================================================

DEFINE TABLE graph_specialty SCHEMAFULL;
DEFINE FIELD slug              ON TABLE graph_specialty TYPE string;
DEFINE FIELD name              ON TABLE graph_specialty TYPE string;
DEFINE FIELD description       ON TABLE graph_specialty TYPE string DEFAULT '';
DEFINE FIELD perspective       ON TABLE graph_specialty TYPE string DEFAULT 'practitioner';
DEFINE FIELD discipline        ON TABLE graph_specialty TYPE option<string>;
DEFINE FIELD insight_count     ON TABLE graph_specialty TYPE int DEFAULT 0;
DEFINE FIELD task_count        ON TABLE graph_specialty TYPE int DEFAULT 0;
DEFINE FIELD graph_id          ON TABLE graph_specialty TYPE string DEFAULT 'default';
DEFINE INDEX idx_gspec_slug    ON TABLE graph_specialty FIELDS slug, graph_id UNIQUE;
DEFINE INDEX idx_gspec_graph   ON TABLE graph_specialty FIELDS graph_id;

DEFINE TABLE graph_agent SCHEMAFULL;
DEFINE FIELD archetype         ON TABLE graph_agent TYPE string DEFAULT 'executor';
DEFINE FIELD mode              ON TABLE graph_agent TYPE string DEFAULT 'reactive';
DEFINE FIELD perspective       ON TABLE graph_agent TYPE string DEFAULT 'practitioner';
DEFINE FIELD specialties       ON TABLE graph_agent TYPE array<string> DEFAULT [];
DEFINE FIELD engagement        ON TABLE graph_agent TYPE option<object>;
DEFINE FIELD task              ON TABLE graph_agent TYPE option<record<graph_task>>;
DEFINE FIELD duration_ms       ON TABLE graph_agent TYPE int DEFAULT 0;
DEFINE FIELD created_at        ON TABLE graph_agent TYPE datetime DEFAULT time::now();
DEFINE FIELD graph_id          ON TABLE graph_agent TYPE string DEFAULT 'default';
DEFINE INDEX idx_gagent_graph  ON TABLE graph_agent FIELDS graph_id;

-- ================================================================
-- SUPPORT NODES
-- ================================================================

DEFINE TABLE graph_document SCHEMAFULL;
DEFINE FIELD title             ON TABLE graph_document TYPE string;
DEFINE FIELD content           ON TABLE graph_document TYPE option<string>;
DEFINE FIELD doc_type          ON TABLE graph_document TYPE string DEFAULT 'other';
DEFINE FIELD path              ON TABLE graph_document TYPE option<string>;
DEFINE FIELD created_at        ON TABLE graph_document TYPE datetime DEFAULT time::now();
DEFINE FIELD graph_id          ON TABLE graph_document TYPE string DEFAULT 'default';
DEFINE INDEX idx_gdoc_graph    ON TABLE graph_document FIELDS graph_id;

DEFINE TABLE graph_user SCHEMAFULL;
DEFINE FIELD name              ON TABLE graph_user TYPE string;
DEFINE FIELD email             ON TABLE graph_user TYPE option<string>;
DEFINE FIELD source            ON TABLE graph_user TYPE string DEFAULT 'git';
    -- git | system | human
DEFINE FIELD commit_count      ON TABLE graph_user TYPE int DEFAULT 0;
DEFINE FIELD first_seen        ON TABLE graph_user TYPE datetime DEFAULT time::now();
DEFINE FIELD last_active       ON TABLE graph_user TYPE option<datetime>;
DEFINE FIELD graph_id          ON TABLE graph_user TYPE string DEFAULT 'default';
DEFINE INDEX idx_guser_name    ON TABLE graph_user FIELDS name, graph_id UNIQUE;
DEFINE INDEX idx_guser_graph   ON TABLE graph_user FIELDS graph_id;

DEFINE TABLE graph_config SCHEMAFULL;
DEFINE FIELD key               ON TABLE graph_config TYPE string;
DEFINE FIELD value             ON TABLE graph_config TYPE string DEFAULT '';
DEFINE FIELD scope             ON TABLE graph_config TYPE string DEFAULT 'graph';
DEFINE FIELD graph_id          ON TABLE graph_config TYPE string DEFAULT 'default';
DEFINE INDEX idx_gconf_key     ON TABLE graph_config FIELDS key, graph_id UNIQUE;

-- ================================================================
-- EDGE TYPES (all used with RELATE syntax)
-- Common fields on all edges: created_at, confidence, source, metadata
-- ================================================================

-- Code relationships
DEFINE TABLE depends_on TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE depends_on TYPE record;
DEFINE FIELD out               ON TABLE depends_on TYPE record;
DEFINE FIELD created_at        ON TABLE depends_on TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE depends_on TYPE float DEFAULT 1.0;
DEFINE FIELD source            ON TABLE depends_on TYPE string DEFAULT 'scanner';
DEFINE FIELD metadata          ON TABLE depends_on TYPE option<object>;
DEFINE INDEX idx_dep_in        ON TABLE depends_on FIELDS in;
DEFINE INDEX idx_dep_out       ON TABLE depends_on FIELDS out;

DEFINE TABLE imports TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE imports TYPE record;
DEFINE FIELD out               ON TABLE imports TYPE record;
DEFINE FIELD import_name       ON TABLE imports TYPE option<string>;
DEFINE FIELD created_at        ON TABLE imports TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE imports TYPE float DEFAULT 1.0;
DEFINE FIELD source            ON TABLE imports TYPE string DEFAULT 'scanner';
DEFINE INDEX idx_imp_in        ON TABLE imports FIELDS in;
DEFINE INDEX idx_imp_out       ON TABLE imports FIELDS out;

DEFINE TABLE tests TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE tests TYPE record;
DEFINE FIELD out               ON TABLE tests TYPE record;
DEFINE FIELD created_at        ON TABLE tests TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE tests TYPE float DEFAULT 0.8;
DEFINE FIELD source            ON TABLE tests TYPE string DEFAULT 'scanner';
DEFINE INDEX idx_tests_in      ON TABLE tests FIELDS in;
DEFINE INDEX idx_tests_out     ON TABLE tests FIELDS out;

DEFINE TABLE implements TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE implements TYPE record;
DEFINE FIELD out               ON TABLE implements TYPE record;
DEFINE FIELD created_at        ON TABLE implements TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE implements TYPE float DEFAULT 0.7;
DEFINE FIELD source            ON TABLE implements TYPE string DEFAULT 'agent';
DEFINE INDEX idx_impl_in       ON TABLE implements FIELDS in;
DEFINE INDEX idx_impl_out      ON TABLE implements FIELDS out;

-- Knowledge relationships
DEFINE TABLE informed_by TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE informed_by TYPE record;
DEFINE FIELD out               ON TABLE informed_by TYPE record;
DEFINE FIELD created_at        ON TABLE informed_by TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE informed_by TYPE float DEFAULT 0.7;
DEFINE FIELD source            ON TABLE informed_by TYPE string DEFAULT 'agent';
DEFINE INDEX idx_infby_in      ON TABLE informed_by FIELDS in;
DEFINE INDEX idx_infby_out     ON TABLE informed_by FIELDS out;

DEFINE TABLE solves TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE solves TYPE record;
DEFINE FIELD out               ON TABLE solves TYPE record;
DEFINE FIELD created_at        ON TABLE solves TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE solves TYPE float DEFAULT 0.7;
DEFINE FIELD source            ON TABLE solves TYPE string DEFAULT 'agent';
DEFINE INDEX idx_solves_in     ON TABLE solves FIELDS in;
DEFINE INDEX idx_solves_out    ON TABLE solves FIELDS out;

DEFINE TABLE causes TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE causes TYPE record;
DEFINE FIELD out               ON TABLE causes TYPE record;
DEFINE FIELD created_at        ON TABLE causes TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE causes TYPE float DEFAULT 0.6;
DEFINE FIELD source            ON TABLE causes TYPE string DEFAULT 'agent';
DEFINE INDEX idx_causes_in     ON TABLE causes FIELDS in;
DEFINE INDEX idx_causes_out    ON TABLE causes FIELDS out;

DEFINE TABLE improves TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE improves TYPE record;
DEFINE FIELD out               ON TABLE improves TYPE record;
DEFINE FIELD created_at        ON TABLE improves TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE improves TYPE float DEFAULT 0.7;
DEFINE FIELD source            ON TABLE improves TYPE string DEFAULT 'agent';
DEFINE INDEX idx_impr_in       ON TABLE improves FIELDS in;
DEFINE INDEX idx_impr_out      ON TABLE improves FIELDS out;

DEFINE TABLE breaks TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE breaks TYPE record;
DEFINE FIELD out               ON TABLE breaks TYPE record;
DEFINE FIELD created_at        ON TABLE breaks TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE breaks TYPE float DEFAULT 0.8;
DEFINE FIELD source            ON TABLE breaks TYPE string DEFAULT 'agent';
DEFINE INDEX idx_breaks_in     ON TABLE breaks FIELDS in;
DEFINE INDEX idx_breaks_out    ON TABLE breaks FIELDS out;

DEFINE TABLE reverts TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE reverts TYPE record;
DEFINE FIELD out               ON TABLE reverts TYPE record;
DEFINE FIELD created_at        ON TABLE reverts TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE reverts TYPE float DEFAULT 0.9;
DEFINE FIELD source            ON TABLE reverts TYPE string DEFAULT 'agent';
DEFINE INDEX idx_rev_in        ON TABLE reverts FIELDS in;
DEFINE INDEX idx_rev_out       ON TABLE reverts FIELDS out;

-- Work relationships
DEFINE TABLE decomposes TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE decomposes TYPE record;
DEFINE FIELD out               ON TABLE decomposes TYPE record;
DEFINE FIELD sequence          ON TABLE decomposes TYPE int DEFAULT 0;
DEFINE FIELD created_at        ON TABLE decomposes TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE decomposes TYPE float DEFAULT 1.0;
DEFINE FIELD source            ON TABLE decomposes TYPE string DEFAULT 'agent';
DEFINE INDEX idx_decomp_in     ON TABLE decomposes FIELDS in;
DEFINE INDEX idx_decomp_out    ON TABLE decomposes FIELDS out;

DEFINE TABLE assigned_to TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE assigned_to TYPE record;
DEFINE FIELD out               ON TABLE assigned_to TYPE record;
DEFINE FIELD created_at        ON TABLE assigned_to TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE assigned_to TYPE float DEFAULT 1.0;
DEFINE FIELD source            ON TABLE assigned_to TYPE string DEFAULT 'system';
DEFINE INDEX idx_assign_in     ON TABLE assigned_to FIELDS in;
DEFINE INDEX idx_assign_out    ON TABLE assigned_to FIELDS out;

DEFINE TABLE produced TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE produced TYPE record;
DEFINE FIELD out               ON TABLE produced TYPE record;
DEFINE FIELD created_at        ON TABLE produced TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE produced TYPE float DEFAULT 0.9;
DEFINE FIELD source            ON TABLE produced TYPE string DEFAULT 'agent';
DEFINE INDEX idx_prod_in       ON TABLE produced FIELDS in;
DEFINE INDEX idx_prod_out      ON TABLE produced FIELDS out;

-- Meta relationships
DEFINE TABLE related_to TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE related_to TYPE record;
DEFINE FIELD out               ON TABLE related_to TYPE record;
DEFINE FIELD strength          ON TABLE related_to TYPE float DEFAULT 0.5;
DEFINE FIELD created_at        ON TABLE related_to TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE related_to TYPE float DEFAULT 0.5;
DEFINE FIELD source            ON TABLE related_to TYPE string DEFAULT 'agent';
DEFINE INDEX idx_rel_in        ON TABLE related_to FIELDS in;
DEFINE INDEX idx_rel_out       ON TABLE related_to FIELDS out;

DEFINE TABLE evolved_from TYPE RELATION SCHEMAFULL;
DEFINE FIELD in                ON TABLE evolved_from TYPE record;
DEFINE FIELD out               ON TABLE evolved_from TYPE record;
DEFINE FIELD version           ON TABLE evolved_from TYPE int DEFAULT 1;
DEFINE FIELD created_at        ON TABLE evolved_from TYPE datetime DEFAULT time::now();
DEFINE FIELD confidence        ON TABLE evolved_from TYPE float DEFAULT 1.0;
DEFINE FIELD source            ON TABLE evolved_from TYPE string DEFAULT 'system';
DEFINE INDEX idx_evol_in       ON TABLE evolved_from FIELDS in;
DEFINE INDEX idx_evol_out      ON TABLE evolved_from FIELDS out;

-- ================================================================
-- GRAPH METADATA
-- ================================================================

-- Track graph instances (default = your codebase, temp_xxx = scanned repos)
DEFINE TABLE graph_instance SCHEMAFULL;
DEFINE FIELD graph_id          ON TABLE graph_instance TYPE string;
DEFINE FIELD name              ON TABLE graph_instance TYPE string;
DEFINE FIELD repo_url          ON TABLE graph_instance TYPE option<string>;
DEFINE FIELD repo_path         ON TABLE graph_instance TYPE option<string>;
DEFINE FIELD mode              ON TABLE graph_instance TYPE string DEFAULT 'permanent';
    -- permanent | temporary
DEFINE FIELD node_count        ON TABLE graph_instance TYPE int DEFAULT 0;
DEFINE FIELD edge_count        ON TABLE graph_instance TYPE int DEFAULT 0;
DEFINE FIELD scanned_at        ON TABLE graph_instance TYPE option<datetime>;
DEFINE FIELD created_at        ON TABLE graph_instance TYPE datetime DEFAULT time::now();
DEFINE FIELD expires_at        ON TABLE graph_instance TYPE option<datetime>;
DEFINE INDEX idx_gi_id         ON TABLE graph_instance FIELDS graph_id UNIQUE;

-- Bump schema version
UPSERT config_entry SET value = '31' WHERE key = 'schema_version';
