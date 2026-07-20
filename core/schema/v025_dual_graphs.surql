-- schema/v025_dual_graphs.surql
-- Dual knowledge graphs: discipline table, specialty evolution, domain_path formalization.
-- Introduces a platform-level org sentinel, a discipline taxonomy table, and expands
-- specialty with perspective, system prompt, bootstrapping metadata, and graph linkage.

-- ── 1. Platform sentinel org ─────────────────────────────────────────────────
-- Provides a home for platform-level specialties not tied to any user org.
-- org is SCHEMAFULL with fields: name, tenant, settings, created_at.
-- tenant:default is the bootstrap tenant created in v001.
UPSERT org:platform SET name = 'Platform', tenant = tenant:default, settings = {}, created_at = time::now();

-- ── 2. Discipline table ───────────────────────────────────────────────────────
-- Top-level taxonomy that groups related specialties (e.g. "Engineering", "Design").
DEFINE TABLE discipline SCHEMAFULL;
DEFINE FIELD slug        ON TABLE discipline TYPE string;
DEFINE FIELD name        ON TABLE discipline TYPE string;
DEFINE FIELD description ON TABLE discipline TYPE string DEFAULT '';
DEFINE FIELD created_at  ON TABLE discipline TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_disc_slug ON TABLE discipline FIELDS slug UNIQUE;

-- ── 3. Specialty table extensions ────────────────────────────────────────────
-- Additive DEFINE FIELD calls safely extend the existing SCHEMAFULL specialty table.
DEFINE FIELD description   ON TABLE specialty TYPE string DEFAULT '';
DEFINE FIELD system_prompt ON TABLE specialty TYPE option<string>;
DEFINE FIELD perspective    ON TABLE specialty TYPE string DEFAULT 'practitioner';
DEFINE FIELD discipline     ON TABLE specialty TYPE option<record<discipline>>;
DEFINE FIELD insight_count  ON TABLE specialty TYPE int DEFAULT 0;
DEFINE FIELD bootstrapped   ON TABLE specialty TYPE bool DEFAULT false;
DEFINE FIELD min_threshold  ON TABLE specialty TYPE int DEFAULT 5;
DEFINE FIELD status         ON TABLE specialty TYPE string DEFAULT 'active';
DEFINE FIELD tags           ON TABLE specialty TYPE array<string> DEFAULT [];
DEFINE INDEX idx_spec_disc  ON TABLE specialty FIELDS discipline, org;
DEFINE INDEX idx_spec_persp ON TABLE specialty FIELDS perspective, org;

-- ── 4. Formalize domain_path on insight ──────────────────────────────────────
-- domain_path was written by the backfill script but never declared in schema.
DEFINE FIELD domain_path ON TABLE insight TYPE option<string>;

-- ── 5. Bump schema version ───────────────────────────────────────────────────
UPSERT config_entry SET value = '25' WHERE key = 'schema_version';
