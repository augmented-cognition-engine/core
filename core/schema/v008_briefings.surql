-- v008: briefings + conflict resolution enhancement
-- Reference: docs/ace-18-complete-schema.md lines 537-548

-- ============================================================
-- BRIEFING — generated intelligence briefings
-- ============================================================
DEFINE TABLE briefing SCHEMAFULL;
DEFINE FIELD org               ON TABLE briefing TYPE record<org>;
DEFINE FIELD workspace         ON TABLE briefing TYPE option<record<workspace>>;
DEFINE FIELD content           ON TABLE briefing TYPE string;
DEFINE FIELD period            ON TABLE briefing TYPE string;
    -- daily | weekly | monthly | on_demand
DEFINE FIELD metrics           ON TABLE briefing TYPE object;
    -- corrections_written, insights_verified, gaps_filled, conflicts_found, etc.
DEFINE FIELD engine_runs       ON TABLE briefing TYPE option<array>;
    -- array of engine_run record IDs summarized in this briefing
DEFINE FIELD created_at        ON TABLE briefing TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_brief_org     ON TABLE briefing FIELDS org, created_at;

-- ============================================================
-- CONFLICT — add resolution_type for structured resolution
-- ============================================================
DEFINE FIELD resolution_type   ON TABLE conflict TYPE option<string>;
    -- keep_a | keep_b | keep_both | merge

UPSERT config_entry SET key = 'schema_version', value = '8'
    WHERE key = 'schema_version';
