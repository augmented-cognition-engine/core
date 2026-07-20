-- v050: Engine schedule overrides
-- Runtime cron/enabled overrides for sentinel engines.
-- Registry default wins when no override exists.

DEFINE TABLE engine_schedule_override SCHEMAFULL;
DEFINE FIELD org ON engine_schedule_override TYPE record<org>;
DEFINE FIELD engine ON engine_schedule_override TYPE string;
DEFINE FIELD cron ON engine_schedule_override TYPE option<string>;
DEFINE FIELD enabled ON engine_schedule_override TYPE bool DEFAULT true;
DEFINE FIELD updated_at ON engine_schedule_override TYPE datetime VALUE time::now();
DEFINE INDEX idx_eso_engine ON engine_schedule_override FIELDS org, engine UNIQUE;

UPSERT config_entry SET value = 'v050'
  WHERE key = 'schema_version';
