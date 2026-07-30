-- v159: finish the runner org-to-product migration.
--
-- Runtime code has selected and written these records by product since the
-- hierarchy rename, but v054-v061 never migrated the two runner tables. SDK 2
-- correctly surfaces the resulting rejected CREATE during API startup.
DEFINE FIELD OVERWRITE org ON runner_config TYPE option<string>;
DEFINE FIELD IF NOT EXISTS product ON runner_config TYPE option<record<product>>;
DEFINE INDEX OVERWRITE idx_rc_org ON runner_config FIELDS product UNIQUE;

DEFINE FIELD OVERWRITE org ON task_queue TYPE option<string>;
DEFINE FIELD IF NOT EXISTS product ON task_queue TYPE option<record<product>>;
DEFINE FIELD OVERWRITE source ON task_queue TYPE string DEFAULT 'user'
    ASSERT $value IN ['user', 'system', 'pm', 'recommendation'];
DEFINE FIELD IF NOT EXISTS metadata ON task_queue TYPE option<object> FLEXIBLE;
DEFINE INDEX OVERWRITE idx_tq_org_status ON task_queue FIELDS product, status;
