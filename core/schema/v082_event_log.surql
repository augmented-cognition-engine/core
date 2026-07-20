-- v082: Event bus audit log
-- Persists last 7 days of in-process events for debugging and replay.
-- Written by AuditLogger (engine/events/audit_logger.py) — NOT by bus.py directly.
-- Retention: 7-day rolling window enforced at write time.

DEFINE TABLE event_log SCHEMALESS;

DEFINE FIELD event_type ON event_log TYPE string;
DEFINE FIELD payload    ON event_log TYPE object;
DEFINE FIELD product    ON event_log TYPE option<string>;
DEFINE FIELD created_at ON event_log TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_el_created     ON event_log FIELDS created_at;
DEFINE INDEX idx_el_product     ON event_log FIELDS product, created_at;
DEFINE INDEX idx_el_event_type  ON event_log FIELDS event_type, created_at;
