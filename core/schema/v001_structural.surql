-- v001: structural tables
-- Reference: docs/ace-04-implementation-guide-1.md §1

-- ================================================================
-- TENANT — the billing entity
-- ================================================================
DEFINE TABLE tenant SCHEMAFULL;
DEFINE FIELD name        ON TABLE tenant TYPE string;
DEFINE FIELD plan        ON TABLE tenant TYPE string DEFAULT 'solo';
DEFINE FIELD settings    ON TABLE tenant TYPE object DEFAULT {};
DEFINE FIELD created_at  ON TABLE tenant TYPE datetime DEFAULT time::now();

-- ================================================================
-- ORGANIZATION — the shared brain boundary
-- ================================================================
DEFINE TABLE org SCHEMAFULL;
DEFINE FIELD name        ON TABLE org TYPE string;
DEFINE FIELD tenant      ON TABLE org TYPE record<tenant>;
DEFINE FIELD settings    ON TABLE org TYPE object DEFAULT {};
DEFINE FIELD created_at  ON TABLE org TYPE datetime DEFAULT time::now();

-- ================================================================
-- USER
-- ================================================================
DEFINE TABLE user SCHEMAFULL;
DEFINE FIELD name        ON TABLE user TYPE string;
DEFINE FIELD email       ON TABLE user TYPE string;
DEFINE FIELD tenant      ON TABLE user TYPE record<tenant>;
DEFINE FIELD created_at  ON TABLE user TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_user_email ON TABLE user FIELDS email UNIQUE;

-- ================================================================
-- WORKSPACE — a perspective on the shared intelligence
-- ================================================================
DEFINE TABLE workspace SCHEMAFULL;
DEFINE FIELD name           ON TABLE workspace TYPE string;
DEFINE FIELD org            ON TABLE workspace TYPE record<org>;
DEFINE FIELD identity       ON TABLE workspace TYPE option<string>;
DEFINE FIELD active_domains ON TABLE workspace TYPE array DEFAULT [];
DEFINE FIELD tools          ON TABLE workspace TYPE array DEFAULT [];
DEFINE FIELD vocabulary     ON TABLE workspace TYPE object DEFAULT {};
DEFINE FIELD constraints    ON TABLE workspace TYPE array DEFAULT [];
DEFINE FIELD schedule       ON TABLE workspace TYPE object DEFAULT {};
DEFINE FIELD created_at     ON TABLE workspace TYPE datetime DEFAULT time::now();

-- ================================================================
-- MEMBERSHIP — who can access what
-- ================================================================
DEFINE TABLE membership SCHEMAFULL;
DEFINE FIELD user       ON TABLE membership TYPE record<user>;
DEFINE FIELD org        ON TABLE membership TYPE record<org>;
DEFINE FIELD workspace  ON TABLE membership TYPE option<record<workspace>>;
DEFINE FIELD role       ON TABLE membership TYPE string DEFAULT 'member';
DEFINE FIELD created_at ON TABLE membership TYPE datetime DEFAULT time::now();

-- ================================================================
-- DOMAIN — a functional area (C-suite mapped)
-- ================================================================
DEFINE TABLE domain SCHEMAFULL;
DEFINE FIELD slug              ON TABLE domain TYPE string;
DEFINE FIELD name              ON TABLE domain TYPE string;
DEFINE FIELD executive         ON TABLE domain TYPE string;
DEFINE FIELD system_prompt     ON TABLE domain TYPE option<string>;
DEFINE FIELD tools             ON TABLE domain TYPE array DEFAULT [];
DEFINE FIELD eval_rubric       ON TABLE domain TYPE object DEFAULT {};
DEFINE FIELD default_clearance ON TABLE domain TYPE string DEFAULT 'open';
DEFINE FIELD org               ON TABLE domain TYPE option<record<org>>;
DEFINE INDEX idx_domain_slug ON TABLE domain FIELDS slug, org UNIQUE;

-- ================================================================
-- SUBDOMAIN — narrower area within a domain
-- ================================================================
DEFINE TABLE subdomain SCHEMAFULL;
DEFINE FIELD slug          ON TABLE subdomain TYPE string;
DEFINE FIELD name          ON TABLE subdomain TYPE string;
DEFINE FIELD domain        ON TABLE subdomain TYPE record<domain>;
DEFINE FIELD system_prompt ON TABLE subdomain TYPE option<string>;
DEFINE FIELD tools         ON TABLE subdomain TYPE array DEFAULT [];
DEFINE FIELD eval_rubric   ON TABLE subdomain TYPE object DEFAULT {};
DEFINE FIELD org           ON TABLE subdomain TYPE option<record<org>>;
DEFINE INDEX idx_sub_slug ON TABLE subdomain FIELDS slug, domain UNIQUE;

-- ================================================================
-- SPECIALTY — emerges from repeated work
-- ================================================================
DEFINE TABLE specialty SCHEMAFULL;
DEFINE FIELD slug        ON TABLE specialty TYPE string;
DEFINE FIELD name        ON TABLE specialty TYPE string;
DEFINE FIELD parents     ON TABLE specialty TYPE array DEFAULT [];
DEFINE FIELD org         ON TABLE specialty TYPE record<org>;
DEFINE FIELD task_count  ON TABLE specialty TYPE int DEFAULT 0;
DEFINE FIELD created_at  ON TABLE specialty TYPE datetime DEFAULT time::now();
DEFINE FIELD last_active ON TABLE specialty TYPE option<datetime>;
DEFINE INDEX idx_spec_slug ON TABLE specialty FIELDS slug, org UNIQUE;

-- ================================================================
-- DOMAIN_FLOW_CONFIG — per-org overrides for intelligence flow
-- ================================================================
DEFINE TABLE domain_flow_config SCHEMAFULL;
DEFINE FIELD domain                ON TABLE domain_flow_config TYPE record<domain>;
DEFINE FIELD org                   ON TABLE domain_flow_config TYPE record<org>;
DEFINE FIELD default_clearance     ON TABLE domain_flow_config TYPE string DEFAULT 'open';
DEFINE FIELD insight_propagation   ON TABLE domain_flow_config TYPE bool DEFAULT true;
DEFINE FIELD consume_org_intel     ON TABLE domain_flow_config TYPE bool DEFAULT true;
DEFINE FIELD contribute_org_intel  ON TABLE domain_flow_config TYPE bool DEFAULT true;
DEFINE INDEX idx_flow_config ON TABLE domain_flow_config FIELDS domain, org UNIQUE;

-- ================================================================
-- CONFIG_ENTRY — schema version tracking
-- ================================================================
DEFINE TABLE config_entry SCHEMAFULL;
DEFINE FIELD key         ON TABLE config_entry TYPE string;
DEFINE FIELD value       ON TABLE config_entry TYPE string;
DEFINE INDEX idx_config_key ON TABLE config_entry FIELDS key UNIQUE;

UPSERT config_entry SET key = 'schema_version', value = '1'
    WHERE key = 'schema_version';
