-- v101: Reasoning journey — long-retention journey_event table + reasoning_edge + voice_thread.originating_event
--
-- Surfaces ACE's cognitive composition layer as a queryable journey of events.
-- event_log keeps its 7-day audit role unchanged; journey_event holds the
-- partner-feel reasoning history (1-year retention via separate sweeper).
-- Each journey_event row carries an optional composition_trace JSON capturing
-- what meta-skills + frame + signals produced the event. A new reasoning_edge
-- table holds inferred causal links between journey_event rows for breadcrumb
-- chains in the /journey UI.

-- (1) journey_event — long-retention partner-history store, mirrors event_log shape
DEFINE TABLE journey_event SCHEMALESS;
DEFINE FIELD topic              ON journey_event TYPE string;
DEFINE FIELD product            ON journey_event TYPE record<product>;
DEFINE FIELD payload            ON journey_event TYPE object;
DEFINE FIELD provenance         ON journey_event TYPE option<object>;
DEFINE FIELD composition_trace  ON journey_event TYPE option<object>;
DEFINE FIELD occurred_at        ON journey_event TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_je_product_time ON journey_event FIELDS product, occurred_at;
DEFINE INDEX idx_je_topic        ON journey_event FIELDS topic;

-- (2) reasoning_edge — directed causal links between journey_event rows
DEFINE TABLE reasoning_edge SCHEMALESS;
DEFINE FIELD from_event   ON reasoning_edge TYPE record<journey_event>;
DEFINE FIELD to_event     ON reasoning_edge TYPE record<journey_event>;
DEFINE FIELD edge_type    ON reasoning_edge TYPE string
  ASSERT $value INSIDE ['triggered', 'referenced', 'escalated_by', 'resolved', 'informed_by_star_trace'];
DEFINE FIELD confidence   ON reasoning_edge TYPE float DEFAULT 1.0;
DEFINE FIELD product      ON reasoning_edge TYPE record<product>;
DEFINE FIELD created_at   ON reasoning_edge TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_re_from        ON reasoning_edge FIELDS from_event;
DEFINE INDEX idx_re_to          ON reasoning_edge FIELDS to_event;
DEFINE INDEX idx_re_product     ON reasoning_edge FIELDS product, created_at;
DEFINE INDEX idx_re_uniq ON reasoning_edge FIELDS from_event, to_event, edge_type UNIQUE;

-- (3) voice_thread.originating_event — deterministic pivot from ThreadRow → /journey
DEFINE FIELD originating_event ON voice_thread TYPE option<record<journey_event>>;

UPDATE config_entry SET value = '101' WHERE key = 'schema_version';
