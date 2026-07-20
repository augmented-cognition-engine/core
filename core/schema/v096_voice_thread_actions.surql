-- v096: Voice thread actions — audit log for partner snooze/commit/resolve
--       + snooze_until field on voice_thread

DEFINE TABLE voice_thread_action SCHEMALESS;
DEFINE FIELD thread_id    ON voice_thread_action TYPE record<voice_thread>;
DEFINE FIELD product      ON voice_thread_action TYPE record<product>;
DEFINE FIELD kind         ON voice_thread_action TYPE string
  ASSERT $value IN ["snooze","resolve","commit"];
DEFINE FIELD snooze_until ON voice_thread_action TYPE option<datetime>;
DEFINE FIELD note         ON voice_thread_action TYPE option<string>;
DEFINE FIELD created_at   ON voice_thread_action TYPE datetime DEFAULT time::now();
-- created_by holds the auth subject (typically user email from the bearer-token
-- session). Optional because system-initiated actions have no user.
DEFINE FIELD created_by   ON voice_thread_action TYPE option<string>;

DEFINE INDEX idx_vta_thread          ON voice_thread_action FIELDS thread_id;
DEFINE INDEX idx_vta_product_created ON voice_thread_action FIELDS product, created_at;

-- Add snooze_until field to existing voice_thread table
DEFINE FIELD snooze_until ON voice_thread TYPE option<datetime>;

UPDATE config_entry SET value = '96' WHERE key = 'schema_version';
