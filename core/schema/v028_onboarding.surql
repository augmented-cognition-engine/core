-- v028_onboarding.surql
-- Onboarding: priority field on specialty for bootstrap ordering

DEFINE FIELD priority ON TABLE specialty TYPE string DEFAULT 'emerged';

UPSERT config_entry SET value = '28' WHERE key = 'schema_version';
