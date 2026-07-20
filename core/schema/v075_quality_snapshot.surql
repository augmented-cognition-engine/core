-- v075: D2 — capability_quality_snapshot for score trend tracking
-- Written alongside (not replacing) the capability_quality UPSERT

DEFINE TABLE capability_quality_snapshot SCHEMALESS;

DEFINE FIELD capability ON TABLE capability_quality_snapshot TYPE record<capability>;
DEFINE FIELD product ON TABLE capability_quality_snapshot TYPE record<product>;
DEFINE FIELD dimension ON TABLE capability_quality_snapshot TYPE string;
DEFINE FIELD score ON TABLE capability_quality_snapshot TYPE float;
DEFINE FIELD confidence ON TABLE capability_quality_snapshot TYPE float DEFAULT 0.5;
DEFINE FIELD gaps_count ON TABLE capability_quality_snapshot TYPE int DEFAULT 0;
DEFINE FIELD assessed_at ON TABLE capability_quality_snapshot TYPE datetime VALUE time::now();

DEFINE INDEX snap_lookup ON TABLE capability_quality_snapshot
    COLUMNS product, capability, dimension, assessed_at;
