-- v049: Add project scoping to operational tables for multi-product workspace
-- All fields are optional — null means org-wide or ecosystem-scoped (backward compatible)

-- SCHEMALESS tables (converted in v032/v044): field definitions added for documentation
DEFINE FIELD project ON capability TYPE option<record<project>>;
DEFINE FIELD project ON idea TYPE option<record<project>>;
DEFINE FIELD project ON briefing TYPE option<record<project>>;
DEFINE FIELD project ON agent_spec TYPE option<record<project>>;
DEFINE FIELD project ON agent_feedback TYPE option<record<project>>;
DEFINE FIELD project ON product_direction TYPE option<record<project>>;

-- SCHEMAFULL tables: field MUST be explicitly defined before writing
DEFINE FIELD project ON capability_quality TYPE option<record<project>>;
DEFINE FIELD project ON capability_scan TYPE option<record<project>>;
DEFINE FIELD project ON initiative TYPE option<record<project>>;
DEFINE FIELD project ON chat_session TYPE option<record<project>>;
DEFINE FIELD project ON notification TYPE option<record<project>>;
DEFINE FIELD project ON agent_session TYPE option<record<project>>;

-- Index changes: allow same slug across different projects
REMOVE INDEX idx_capability_org_slug ON TABLE capability;
DEFINE INDEX idx_capability_org_proj_slug ON capability FIELDS org, project, slug UNIQUE;

-- Update capability_quality unique index to include project
REMOVE INDEX idx_cq_org_dim_cap ON TABLE capability_quality;
DEFINE INDEX idx_cq_org_proj_dim_cap ON capability_quality FIELDS org, project, dimension, capability UNIQUE;

-- Update notification index to support per-project badge queries
DEFINE INDEX idx_notif_project ON notification FIELDS org, project, read, tier, created_at;

-- Version bump
UPSERT config_entry SET value = "v049" WHERE key = "schema_version";
