-- v016: Portal enhancements
DEFINE FIELD IF NOT EXISTS starred ON idea TYPE bool DEFAULT false;

-- Bump schema version
UPDATE config_entry SET value = '16' WHERE key = 'schema_version';
