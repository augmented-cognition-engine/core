-- schema/v123_graph_tension_event.surql
-- Telemetry: every surfaced graph tension/consequence, trace-linked, for the
-- intelligence-curve / ROI evidence (join with reasoning outcomes later).
DEFINE FIELD from_insight ON graph_tension_event TYPE string;
DEFINE FIELD to_insight ON graph_tension_event TYPE string;
DEFINE FIELD relationship ON graph_tension_event TYPE string;
DEFINE FIELD surface ON graph_tension_event TYPE string;       -- reasoning_context | ace_load
DEFINE FIELD product ON graph_tension_event TYPE option<string>;
DEFINE FIELD trace_id ON graph_tension_event TYPE option<string>;
DEFINE FIELD created_at ON graph_tension_event TYPE datetime DEFAULT time::now();
DEFINE INDEX graph_tension_event_product_ts ON TABLE graph_tension_event COLUMNS product, created_at;
