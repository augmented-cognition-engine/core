-- v030: Competitive intelligence observer
-- competitor: registry of tracked competitors and their sources
-- competitive_signal: extracted signals from competitor scans

DEFINE TABLE competitor SCHEMAFULL;
DEFINE FIELD name ON competitor TYPE string;
DEFINE FIELD tier ON competitor TYPE int ASSERT $value >= 1 AND $value <= 3;
DEFINE FIELD sources ON competitor TYPE array;
DEFINE FIELD sources.* ON competitor TYPE object;
DEFINE FIELD sources.*.type ON competitor TYPE string;
DEFINE FIELD sources.*.url ON competitor TYPE string;
DEFINE FIELD domains ON competitor TYPE array;
DEFINE FIELD domains.* ON competitor TYPE string;
DEFINE FIELD org ON competitor TYPE string;
DEFINE FIELD last_scanned ON competitor TYPE option<datetime>;
DEFINE FIELD created_at ON competitor TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_competitor_org ON competitor FIELDS org;
DEFINE INDEX idx_competitor_name ON competitor FIELDS org, name UNIQUE;

DEFINE TABLE competitive_signal SCHEMAFULL;
DEFINE FIELD competitor ON competitive_signal TYPE string;
DEFINE FIELD org ON competitive_signal TYPE string;
DEFINE FIELD title ON competitive_signal TYPE string;
DEFINE FIELD description ON competitive_signal TYPE string;
DEFINE FIELD source_url ON competitive_signal TYPE string;
DEFINE FIELD relevance ON competitive_signal TYPE string;
DEFINE FIELD relevance_score ON competitive_signal TYPE float;
DEFINE FIELD action ON competitive_signal TYPE string;
DEFINE FIELD urgency ON competitive_signal TYPE string;
DEFINE FIELD rationale ON competitive_signal TYPE option<string>;
DEFINE FIELD insight_id ON competitive_signal TYPE option<string>;
DEFINE FIELD created_at ON competitive_signal TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_signal_org ON competitive_signal FIELDS org;
DEFINE INDEX idx_signal_competitor ON competitive_signal FIELDS org, competitor;

-- Bump schema version
UPDATE config_entry SET value = '30' WHERE key = 'schema_version';
