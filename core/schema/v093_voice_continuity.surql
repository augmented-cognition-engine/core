-- v093: Voice continuity layer (per voice rendering v2.0 spec)

DEFINE TABLE voice_thread SCHEMALESS;
DEFINE FIELD topic                 ON voice_thread TYPE string;
DEFINE FIELD product               ON voice_thread TYPE record<product>;
DEFINE FIELD status                ON voice_thread TYPE string;  -- open|resolved|stale
DEFINE FIELD raised_at             ON voice_thread TYPE datetime;
DEFINE FIELD last_referenced_at    ON voice_thread TYPE datetime;
DEFINE FIELD last_state_changed_at ON voice_thread TYPE datetime;
DEFINE FIELD mention_count         ON voice_thread TYPE int DEFAULT 0;
DEFINE FIELD current_payload_hash  ON voice_thread TYPE string;
DEFINE FIELD primary_event_type    ON voice_thread TYPE string;
DEFINE INDEX idx_vt_topic_product  ON voice_thread FIELDS product, topic UNIQUE;
DEFINE INDEX idx_vt_status         ON voice_thread FIELDS product, status, last_state_changed_at;

DEFINE TABLE voice_thread_event SCHEMALESS;
DEFINE FIELD thread       ON voice_thread_event TYPE record<voice_thread>;
DEFINE FIELD product      ON voice_thread_event TYPE record<product>;
DEFINE FIELD occurred_at  ON voice_thread_event TYPE datetime DEFAULT time::now();
DEFINE FIELD kind         ON voice_thread_event TYPE string;
DEFINE FIELD details      ON voice_thread_event TYPE object;
DEFINE INDEX idx_vte_thread       ON voice_thread_event FIELDS thread, occurred_at;
DEFINE INDEX idx_vte_product_kind ON voice_thread_event FIELDS product, kind, occurred_at;

DEFINE TABLE voice_audit SCHEMALESS;
DEFINE FIELD product        ON voice_audit TYPE record<product>;
DEFINE FIELD thread         ON voice_audit TYPE option<record<voice_thread>>;
DEFINE FIELD detected_at    ON voice_audit TYPE datetime DEFAULT time::now();
DEFINE FIELD kind           ON voice_audit TYPE string;
DEFINE FIELD candidate_line ON voice_audit TYPE string;
DEFINE FIELD details        ON voice_audit TYPE object;
DEFINE INDEX idx_va_product_kind ON voice_audit FIELDS product, kind, detected_at;

UPDATE config_entry SET value = '93' WHERE key = 'schema_version';
