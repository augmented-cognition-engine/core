-- Generic, bounded receipt for extension-owned context resolution and outcomes.
-- The task remains the lifecycle authority; this additive projection records
-- capability identity, attempt lineage, input references, and provenance.

DEFINE FIELD IF NOT EXISTS extension_invocation ON TABLE task TYPE option<object>;
DEFINE FIELD IF NOT EXISTS extension_receipt ON TABLE task TYPE option<object>;
DEFINE FIELD IF NOT EXISTS retry_of_task_id ON TABLE task TYPE option<string>;
DEFINE FIELD IF NOT EXISTS cancellation ON TABLE task TYPE option<object>;
DEFINE INDEX IF NOT EXISTS task_extension_retry_parent ON TABLE task FIELDS retry_of_task_id;
