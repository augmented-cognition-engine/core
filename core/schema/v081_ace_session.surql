-- v081: ace_session — worker session state for context-aware classification
-- SCHEMALESS: fields are open-ended; LLM classification dict changes over time.
-- No typed DEFINE FIELD — partial UPSERTs (on_message, update_classification)
-- would fail if any field constraint is missing on first insert.

DEFINE TABLE ace_session SCHEMALESS;

DEFINE INDEX ace_session_session_id ON ace_session FIELDS session_id UNIQUE;

UPDATE config_entry SET value = 81 WHERE key = 'schema_version';
