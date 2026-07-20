-- v014: Portal complete — chat, notifications, document versioning
-- Reference: docs/ace-07-user-experience.md (Home interface, notification model)

-- ============================================================
-- CHAT_SESSION — conversation threads
-- ============================================================
DEFINE TABLE chat_session SCHEMAFULL;
DEFINE FIELD org              ON TABLE chat_session TYPE record<org>;
DEFINE FIELD workspace        ON TABLE chat_session TYPE record<workspace>;
DEFINE FIELD user             ON TABLE chat_session TYPE record<user>;
DEFINE FIELD title            ON TABLE chat_session TYPE option<string>;
DEFINE FIELD status           ON TABLE chat_session TYPE string DEFAULT 'active';
DEFINE FIELD message_count    ON TABLE chat_session TYPE int DEFAULT 0;
DEFINE FIELD created_at       ON TABLE chat_session TYPE datetime DEFAULT time::now();
DEFINE FIELD last_message_at  ON TABLE chat_session TYPE option<datetime>;
DEFINE INDEX idx_chat_session ON TABLE chat_session FIELDS org, user, status, last_message_at;

-- ============================================================
-- CHAT_MESSAGE — individual messages in a session
-- ============================================================
DEFINE TABLE chat_message SCHEMAFULL;
DEFINE FIELD session           ON TABLE chat_message TYPE record<chat_session>;
DEFINE FIELD role              ON TABLE chat_message TYPE string;
DEFINE FIELD content           ON TABLE chat_message TYPE string;
DEFINE FIELD task              ON TABLE chat_message TYPE option<record<task>>;
DEFINE FIELD classification    ON TABLE chat_message TYPE option<object>;
DEFINE FIELD created_at        ON TABLE chat_message TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_chat_msg      ON TABLE chat_message FIELDS session, created_at;

-- ============================================================
-- NOTIFICATION — tiered notification records
-- ============================================================
DEFINE TABLE notification SCHEMAFULL;
DEFINE FIELD org              ON TABLE notification TYPE record<org>;
DEFINE FIELD user             ON TABLE notification TYPE record<user>;
DEFINE FIELD workspace        ON TABLE notification TYPE option<record<workspace>>;
DEFINE FIELD tier             ON TABLE notification TYPE string;
DEFINE FIELD category         ON TABLE notification TYPE string;
DEFINE FIELD title            ON TABLE notification TYPE string;
DEFINE FIELD body             ON TABLE notification TYPE option<string>;
DEFINE FIELD link             ON TABLE notification TYPE option<string>;
DEFINE FIELD source_record    ON TABLE notification TYPE option<string>;
DEFINE FIELD read             ON TABLE notification TYPE bool DEFAULT false;
DEFINE FIELD dismissed        ON TABLE notification TYPE bool DEFAULT false;
DEFINE FIELD delivered_via    ON TABLE notification TYPE array DEFAULT [];
DEFINE FIELD created_at       ON TABLE notification TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_notif_user   ON TABLE notification FIELDS org, user, read, created_at;
DEFINE INDEX idx_notif_tier   ON TABLE notification FIELDS org, user, tier, created_at;

-- ============================================================
-- NOTIFICATION_PREF — per-user delivery preferences
-- ============================================================
DEFINE TABLE notification_pref SCHEMAFULL;
DEFINE FIELD org              ON TABLE notification_pref TYPE record<org>;
DEFINE FIELD user             ON TABLE notification_pref TYPE record<user>;
DEFINE FIELD tier             ON TABLE notification_pref TYPE string;
DEFINE FIELD channels         ON TABLE notification_pref TYPE array DEFAULT [];
DEFINE FIELD email            ON TABLE notification_pref TYPE option<string>;
DEFINE FIELD webhook_url      ON TABLE notification_pref TYPE option<string>;
DEFINE FIELD enabled          ON TABLE notification_pref TYPE bool DEFAULT true;
DEFINE INDEX idx_notifpref    ON TABLE notification_pref FIELDS org, user, tier UNIQUE;

-- ============================================================
-- DOCUMENT_VERSION — copy-on-write document history
-- ============================================================
DEFINE TABLE document_version SCHEMAFULL;
DEFINE FIELD org              ON TABLE document_version TYPE record<org>;
DEFINE FIELD document         ON TABLE document_version TYPE record<document>;
DEFINE FIELD version          ON TABLE document_version TYPE int;
DEFINE FIELD content          ON TABLE document_version TYPE string;
DEFINE FIELD edited_by        ON TABLE document_version TYPE record<user>;
DEFINE FIELD created_at       ON TABLE document_version TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_docver       ON TABLE document_version FIELDS document, version;

-- Bump schema version
UPSERT config_entry SET key = 'schema_version', value = '14'
    WHERE key = 'schema_version';
