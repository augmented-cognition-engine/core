-- v076: D6 — correlation_signal for cross-discipline leading indicators
-- Populated by correlation_engine (weekly). Requires 60+ days of D2 snapshot data.

DEFINE TABLE correlation_signal SCHEMALESS;

DEFINE FIELD product ON TABLE correlation_signal TYPE record<product>;
DEFINE FIELD dimension_a ON TABLE correlation_signal TYPE string;
DEFINE FIELD dimension_b ON TABLE correlation_signal TYPE string;
DEFINE FIELD lag_weeks ON TABLE correlation_signal TYPE int;
DEFINE FIELD correlation_coefficient ON TABLE correlation_signal TYPE float;
DEFINE FIELD interpretation ON TABLE correlation_signal TYPE string;
DEFINE FIELD computed_at ON TABLE correlation_signal TYPE datetime VALUE time::now();
DEFINE FIELD snapshot_count ON TABLE correlation_signal TYPE int;

DEFINE INDEX corr_product ON TABLE correlation_signal FIELDS product, dimension_a, dimension_b;
