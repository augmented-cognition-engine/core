-- v029_domain_path_optional.surql
-- Make domain_path optional everywhere (routing now uses specialties)

DEFINE FIELD domain_path ON TABLE task TYPE option<string> DEFAULT '';
DEFINE FIELD domain_path ON TABLE work_item TYPE option<string> DEFAULT '';
DEFINE FIELD domain_path ON TABLE playbook TYPE option<string> DEFAULT '';
DEFINE FIELD domain_path ON TABLE task_queue TYPE option<string> DEFAULT '';
DEFINE FIELD domain_path ON TABLE experiment_log TYPE option<string> DEFAULT '';
DEFINE FIELD domain_path ON TABLE autonomy_level TYPE option<string> DEFAULT '';

UPSERT config_entry SET value = '29' WHERE key = 'schema_version';
