-- v099: Add seed_origin field to briefing for synthetic-data tracking
--
-- Context:
--   - v097 added seed_origin to capability_quality (SCHEMAFULL).
--   - v098 added seed_origin to capability (SCHEMAFULL despite v044's intent).
--   - briefing is ALSO SCHEMAFULL in the live DB (despite v044's declaration),
--     so synthetic seed rows cannot set the seed_origin field. The seed
--     module at scripts/seed_data/partner_feel_history/briefings.py and
--     the cleanup helper both rely on this field.
--   - Mirror v097/v098 pattern: declare the field as option<string> so existing
--     rows continue to validate.

DEFINE FIELD seed_origin ON briefing TYPE option<string>;

UPDATE config_entry SET value = '99' WHERE key = 'schema_version';
