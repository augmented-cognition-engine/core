-- v017: Runner daemon tables

-- task_queue: unified work queue
DEFINE TABLE IF NOT EXISTS task_queue SCHEMAFULL;
DEFINE FIELD org ON task_queue TYPE string;
DEFINE FIELD IF NOT EXISTS title ON task_queue TYPE string DEFAULT '';
DEFINE FIELD IF NOT EXISTS description ON task_queue TYPE string;
DEFINE FIELD IF NOT EXISTS domain_path ON task_queue TYPE string DEFAULT '';
DEFINE FIELD IF NOT EXISTS priority ON task_queue TYPE int DEFAULT 100;
DEFINE FIELD IF NOT EXISTS status ON task_queue TYPE string DEFAULT 'queued'
    ASSERT $value IN ['queued', 'running', 'completed', 'failed', 'blocked', 'backlog', 'review', 'cancelled'];
DEFINE FIELD IF NOT EXISTS source ON task_queue TYPE string DEFAULT 'user'
    ASSERT $value IN ['user', 'system', 'pm'];
DEFINE FIELD IF NOT EXISTS dependencies ON task_queue TYPE array DEFAULT [];
DEFINE FIELD IF NOT EXISTS work_item_id ON task_queue TYPE option<string>;
DEFINE FIELD IF NOT EXISTS initiative_id ON task_queue TYPE option<string>;
DEFINE FIELD IF NOT EXISTS task_id ON task_queue TYPE option<string>;
DEFINE FIELD IF NOT EXISTS slot_number ON task_queue TYPE option<int>;
DEFINE FIELD IF NOT EXISTS config ON task_queue TYPE option<object> FLEXIBLE;
DEFINE FIELD IF NOT EXISTS cost ON task_queue TYPE float DEFAULT 0.0;
DEFINE FIELD IF NOT EXISTS error ON task_queue TYPE option<string>;
DEFINE FIELD IF NOT EXISTS output ON task_queue TYPE option<string>;
DEFINE FIELD IF NOT EXISTS created_at ON task_queue TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS started_at ON task_queue TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS completed_at ON task_queue TYPE option<datetime>;
DEFINE INDEX IF NOT EXISTS idx_tq_org_status ON task_queue FIELDS org, status;
DEFINE INDEX IF NOT EXISTS idx_tq_priority ON task_queue FIELDS priority;

-- runner_config: singleton per org
DEFINE TABLE IF NOT EXISTS runner_config SCHEMAFULL;
DEFINE FIELD org ON runner_config TYPE string;
DEFINE FIELD IF NOT EXISTS max_concurrent ON runner_config TYPE int DEFAULT 3;
DEFINE FIELD IF NOT EXISTS mode ON runner_config TYPE string DEFAULT 'all'
    ASSERT $value IN ['all', 'user_only', 'paused'];
DEFINE FIELD IF NOT EXISTS auto_approve ON runner_config TYPE bool DEFAULT true;
DEFINE FIELD IF NOT EXISTS status ON runner_config TYPE string DEFAULT 'running'
    ASSERT $value IN ['running', 'stopped', 'paused'];
DEFINE FIELD IF NOT EXISTS daily_cost ON runner_config TYPE float DEFAULT 0.0;
DEFINE FIELD IF NOT EXISTS updated_at ON runner_config TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS idx_rc_org ON runner_config FIELDS org UNIQUE;

-- Bump schema version
UPDATE config_entry SET value = '17' WHERE key = 'schema_version';
