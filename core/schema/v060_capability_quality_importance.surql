-- v060: Add importance field to capability_quality
-- importance: how critical this discipline is for this specific capability (0.0–1.0)
-- Used to prioritize gaps — a security gap in an auth capability matters more than
-- a documentation gap in a utility helper.

DEFINE FIELD importance ON capability_quality TYPE option<float>;

-- Bump schema version
UPDATE config_entry SET value = '60' WHERE key = 'schema_version';
