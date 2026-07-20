-- v018: Chat linked sessions
DEFINE FIELD IF NOT EXISTS linked_to ON chat_session TYPE option<string>;
DEFINE FIELD IF NOT EXISTS linked_type ON chat_session TYPE option<string>;
UPDATE config_entry SET value = '18' WHERE key = 'schema_version';
