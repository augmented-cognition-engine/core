-- v098: Add seed_origin field to capability for synthetic-data tracking
--
-- Context:
--   - v097 added seed_origin to capability_quality (SCHEMAFULL).
--   - capability is also SCHEMAFULL in the live DB (despite v044's intent),
--     so synthetic seed rows cannot set the seed_origin field. The cleanup
--     helper at scripts/seed_data/partner_feel_history/cleanup.py also relies
--     on this field for surgical synthetic-only deletions.
--   - Mirror v097's pattern: declare the field as option<string> so existing
--     rows continue to validate.

DEFINE FIELD seed_origin ON capability TYPE option<string>;

UPDATE config_entry SET value = '98' WHERE key = 'schema_version';
