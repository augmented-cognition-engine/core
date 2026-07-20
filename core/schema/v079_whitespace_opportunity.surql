-- v079: Whitespace opportunities — scored market gaps where ACE can differentiate.
--
-- Whitespace Score = pain_intensity × user_count
--                  × (1 - max_competitor_coverage)
--                  × feasibility_coefficient
--                  × timing_coefficient
--
-- All coefficients are floats in [0, 1]. Higher score = better opportunity.
-- Recomputed weekly by the whitespace_engine sentinel after competitive scans.

DEFINE TABLE whitespace_opportunity SCHEMALESS;

DEFINE FIELD product               ON TABLE whitespace_opportunity TYPE record<product>;
DEFINE FIELD slug                  ON TABLE whitespace_opportunity TYPE string;
DEFINE FIELD title                 ON TABLE whitespace_opportunity TYPE string;
DEFINE FIELD description           ON TABLE whitespace_opportunity TYPE option<string>;
DEFINE FIELD source                ON TABLE whitespace_opportunity TYPE string
    ASSERT $value IN ["competitor_blindspot", "user_pain", "ecosystem_gap", "seeded"];
DEFINE FIELD pain_intensity        ON TABLE whitespace_opportunity TYPE float DEFAULT 0.5;
DEFINE FIELD user_count            ON TABLE whitespace_opportunity TYPE float DEFAULT 0.5;
DEFINE FIELD max_competitor_coverage ON TABLE whitespace_opportunity TYPE float DEFAULT 0.0;
DEFINE FIELD feasibility_coefficient ON TABLE whitespace_opportunity TYPE float DEFAULT 0.7;
DEFINE FIELD timing_coefficient    ON TABLE whitespace_opportunity TYPE float DEFAULT 0.6;
DEFINE FIELD whitespace_score      ON TABLE whitespace_opportunity TYPE float DEFAULT 0.0;
DEFINE FIELD computed_at           ON TABLE whitespace_opportunity VALUE time::now() READONLY;

DEFINE INDEX ws_lookup ON TABLE whitespace_opportunity
    FIELDS product, slug UNIQUE;
DEFINE INDEX ws_score  ON TABLE whitespace_opportunity
    FIELDS product, whitespace_score;

-- Update schema version
UPDATE config_entry SET value = '79' WHERE key = 'schema_version';
