-- v077: Capability matrix — competitor × capability coverage tracking.
--
-- Each row tracks whether a specific competitor covers a capability from our
-- product map. Coverage values: "full" (✓), "partial" (○), "none" (✗).
-- Updated automatically when the competitive_observer classifies signals as
-- "overlap" (they have it) and by ace_competitor_matrix() assessments.

DEFINE TABLE competitor_capability SCHEMALESS;

DEFINE FIELD competitor     ON TABLE competitor_capability TYPE string;  -- competitor name
DEFINE FIELD capability_slug ON TABLE competitor_capability TYPE string;
DEFINE FIELD coverage       ON TABLE competitor_capability TYPE string   -- "full"|"partial"|"none"
    DEFAULT "none"
    ASSERT $value IN ["full", "partial", "none"];
DEFINE FIELD notes          ON TABLE competitor_capability TYPE option<string>;
DEFINE FIELD source_signal  ON TABLE competitor_capability TYPE option<string>;  -- signal ID that triggered update
DEFINE FIELD product        ON TABLE competitor_capability TYPE record<product>;
DEFINE FIELD updated_at     ON TABLE competitor_capability VALUE time::now() READONLY;

DEFINE INDEX cc_lookup ON TABLE competitor_capability
    FIELDS product, competitor, capability_slug UNIQUE;
DEFINE INDEX cc_product ON TABLE competitor_capability FIELDS product;

-- Update schema version
UPDATE config_entry SET value = '77' WHERE key = 'schema_version';
