-- ACE 1.1: append-only receipts for explicit legacy assertion-history mapping.
-- Historical migrations remain immutable; operational cleanup is performed by
-- the bounded dry-run-first upgrade commands.

DEFINE TABLE IF NOT EXISTS assertion_history_upgrade_receipt SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE FIELD IF NOT EXISTS contract ON assertion_history_upgrade_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS component_id ON assertion_history_upgrade_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS target_product ON assertion_history_upgrade_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS source_row_ids ON assertion_history_upgrade_receipt TYPE array<string>;
DEFINE FIELD IF NOT EXISTS created_row_ids ON assertion_history_upgrade_receipt TYPE array<string>;
DEFINE FIELD IF NOT EXISTS proposal_id_map ON assertion_history_upgrade_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS assertion_id_map ON assertion_history_upgrade_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS review_id_map ON assertion_history_upgrade_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS operational ON assertion_history_upgrade_receipt TYPE bool ASSERT $value = false;
DEFINE FIELD IF NOT EXISTS created_at ON assertion_history_upgrade_receipt TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS idx_assertion_history_upgrade_component ON assertion_history_upgrade_receipt
    FIELDS component_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_assertion_history_upgrade_product ON assertion_history_upgrade_receipt
    FIELDS target_product, created_at;

DEFINE TABLE IF NOT EXISTS assertion_history_upgrade_quarantine SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE FIELD IF NOT EXISTS contract ON assertion_history_upgrade_quarantine TYPE string;
DEFINE FIELD IF NOT EXISTS component_id ON assertion_history_upgrade_quarantine TYPE string;
DEFINE FIELD IF NOT EXISTS target_product ON assertion_history_upgrade_quarantine TYPE option<record<product>>;
DEFINE FIELD IF NOT EXISTS source_row_ids ON assertion_history_upgrade_quarantine TYPE array<string>;
DEFINE FIELD IF NOT EXISTS reasons ON assertion_history_upgrade_quarantine TYPE array<string>;
DEFINE FIELD IF NOT EXISTS created_at ON assertion_history_upgrade_quarantine TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS idx_assertion_history_quarantine_component ON assertion_history_upgrade_quarantine
    FIELDS component_id UNIQUE;

UPDATE config_entry SET `value` = '179' WHERE key = 'schema_version';
