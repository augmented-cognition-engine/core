-- v053_code_intelligence.surql
-- Phase 3 LLM analysis results on the code graph.
-- Adds intelligence fields to graph_file, and two new tables for
-- module-level and architecture-level synthesis.

-- ================================================================
-- Phase 3a — per-file LLM analysis (added to graph_file)
-- graph_file is SCHEMAFULL so we explicitly define each field.
-- ================================================================

DEFINE FIELD purpose            ON TABLE graph_file TYPE option<string>;
DEFINE FIELD discipline         ON TABLE graph_file TYPE option<string>;
DEFINE FIELD quality_risks      ON TABLE graph_file TYPE option<array<string>>;
DEFINE FIELD key_exports        ON TABLE graph_file TYPE option<array<string>>;
DEFINE FIELD architectural_role ON TABLE graph_file TYPE option<string>;
DEFINE FIELD analysis_model     ON TABLE graph_file TYPE option<string>;
DEFINE FIELD analyzed_at        ON TABLE graph_file TYPE option<datetime>;

-- ================================================================
-- Phase 3b — module-level synthesis
-- One record per directory group (e.g. "engine/intelligence")
-- ================================================================

DEFINE TABLE graph_module SCHEMALESS;
DEFINE FIELD module_path        ON TABLE graph_module TYPE string;
DEFINE FIELD graph_id           ON TABLE graph_module TYPE string DEFAULT 'default';
DEFINE FIELD purpose            ON TABLE graph_module TYPE option<string>;
DEFINE FIELD key_files          ON TABLE graph_module TYPE option<array<string>>;
DEFINE FIELD internal_patterns  ON TABLE graph_module TYPE option<array<string>>;
DEFINE FIELD quality_gaps       ON TABLE graph_module TYPE option<array<string>>;
DEFINE FIELD dependencies       ON TABLE graph_module TYPE option<array<string>>;
DEFINE FIELD risk_summary       ON TABLE graph_module TYPE option<string>;
DEFINE FIELD synthesized_at     ON TABLE graph_module TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_gmod_path      ON TABLE graph_module FIELDS module_path, graph_id UNIQUE;
DEFINE INDEX idx_gmod_graph     ON TABLE graph_module FIELDS graph_id;

-- ================================================================
-- Phase 3c — architectural overview
-- One record per graph_id — the top-level synthesis
-- ================================================================

DEFINE TABLE graph_architecture SCHEMALESS;
DEFINE FIELD graph_id           ON TABLE graph_architecture TYPE string;
DEFINE FIELD subsystems         ON TABLE graph_architecture TYPE option<array>;
DEFINE FIELD critical_paths     ON TABLE graph_architecture TYPE option<array<string>>;
DEFINE FIELD cross_cutting      ON TABLE graph_architecture TYPE option<array<string>>;
DEFINE FIELD quality_gaps       ON TABLE graph_architecture TYPE option<array>;
DEFINE FIELD architectural_risks ON TABLE graph_architecture TYPE option<array<string>>;
DEFINE FIELD synthesized_at     ON TABLE graph_architecture TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_garch_graph    ON TABLE graph_architecture FIELDS graph_id UNIQUE;

-- Bump schema version
UPSERT config_entry SET value = '53' WHERE key = 'schema_version';
