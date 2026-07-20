-- schema/v024_experiment_narratives.surql
-- Extend experiment_log with best example pairs and narrative fields.

DEFINE FIELD IF NOT EXISTS best_example_control ON experiment_log TYPE option<string>;
DEFINE FIELD IF NOT EXISTS best_example_variant ON experiment_log TYPE option<string>;
DEFINE FIELD IF NOT EXISTS best_example_task ON experiment_log TYPE option<string>;
DEFINE FIELD IF NOT EXISTS narrative_why ON experiment_log TYPE option<string>;
DEFINE FIELD IF NOT EXISTS narrative_what_changed ON experiment_log TYPE option<string>;
DEFINE FIELD IF NOT EXISTS narrative_impact ON experiment_log TYPE option<string>;
DEFINE FIELD IF NOT EXISTS metrics ON experiment_log TYPE option<object>;
DEFINE FIELD IF NOT EXISTS experiment_type ON experiment_log TYPE option<string>;

UPDATE config_entry SET value = '24' WHERE key = 'schema_version';
