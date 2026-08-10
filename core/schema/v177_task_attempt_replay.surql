-- Durable, domain-neutral attempt identity for direct and extension task receipts.
-- The task row remains the lifecycle authority; this object records immutable
-- predecessor/root lineage and the one successor chosen by retry orchestration.

DEFINE FIELD IF NOT EXISTS attempt ON TABLE task TYPE option<object>;
DEFINE INDEX IF NOT EXISTS task_attempt_root ON TABLE task FIELDS attempt.root_task_id;
UPDATE config_entry SET value = '177' WHERE key = 'schema_version';
