-- v158: framework object fields must accept nested keys.
--
-- The shipped seed library writes nested maps into these fields. SCHEMAFULL
-- rejected every framework CREATE while they were plain `TYPE object`, leaving
-- the table empty and forcing reasoning to use PromptFusion's fallback text.
--
-- The full declaration also repairs installations whose version marker
-- advanced despite the legacy v011 table creation having failed.
DEFINE TABLE IF NOT EXISTS framework SCHEMAFULL;

DEFINE FIELD IF NOT EXISTS product            ON framework TYPE option<record<product>>;
DEFINE FIELD IF NOT EXISTS slug               ON framework TYPE string;
DEFINE FIELD IF NOT EXISTS name               ON framework TYPE string;
DEFINE FIELD IF NOT EXISTS family             ON framework TYPE string;
DEFINE FIELD IF NOT EXISTS tier               ON framework TYPE string;
DEFINE FIELD IF NOT EXISTS description        ON framework TYPE string;
DEFINE FIELD IF NOT EXISTS system_prompt      ON framework TYPE string;
DEFINE FIELD IF NOT EXISTS activation_signals ON framework TYPE array;
DEFINE FIELD OVERWRITE archetype_affinity     ON framework TYPE object FLEXIBLE;
DEFINE FIELD OVERWRITE mode_affinity          ON framework TYPE object FLEXIBLE;
DEFINE FIELD OVERWRITE composability          ON framework TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at         ON framework TYPE datetime DEFAULT time::now();

DEFINE INDEX OVERWRITE idx_fw_slug   ON framework FIELDS product, slug UNIQUE;
DEFINE INDEX OVERWRITE idx_fw_family ON framework FIELDS product, family;
