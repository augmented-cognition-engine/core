-- v033: Ecosystem & Project Hierarchy
-- Universal → Ecosystem → Product → Feature

-- Ecosystem: connected set of products sharing conventions
DEFINE TABLE ecosystem SCHEMALESS;
DEFINE FIELD org ON ecosystem TYPE record<org>;
DEFINE FIELD name ON ecosystem TYPE string;
DEFINE FIELD slug ON ecosystem TYPE string;
DEFINE FIELD description ON ecosystem TYPE option<string>;
DEFINE FIELD conventions ON ecosystem TYPE option<object>;
DEFINE FIELD roadmap ON ecosystem TYPE option<object>;
DEFINE FIELD created_at ON ecosystem TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON ecosystem TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_eco_org ON ecosystem FIELDS org;
DEFINE INDEX idx_eco_slug ON ecosystem FIELDS org, slug UNIQUE;

-- Project: a codebase (standalone or within an ecosystem)
DEFINE TABLE project SCHEMALESS;
DEFINE FIELD org ON project TYPE record<org>;
DEFINE FIELD ecosystem ON project TYPE option<record<ecosystem>>;
DEFINE FIELD name ON project TYPE string;
DEFINE FIELD slug ON project TYPE string;
DEFINE FIELD description ON project TYPE option<string>;
DEFINE FIELD repo_path ON project TYPE option<string>;
DEFINE FIELD product_type ON project TYPE option<string>;
DEFINE FIELD active_disciplines ON project TYPE option<array<string>>;
DEFINE FIELD created_at ON project TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON project TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_proj_org ON project FIELDS org;
DEFINE INDEX idx_proj_slug ON project FIELDS org, slug UNIQUE;
DEFINE INDEX idx_proj_eco ON project FIELDS ecosystem;

-- Cross-project dependency
DEFINE TABLE cross_project_dep TYPE RELATION SCHEMALESS;
DEFINE FIELD dep_type ON cross_project_dep TYPE string;
DEFINE FIELD created_at ON cross_project_dep TYPE datetime DEFAULT time::now();

-- Bump schema version
UPDATE config_entry SET value = '33' WHERE key = 'schema_version';
