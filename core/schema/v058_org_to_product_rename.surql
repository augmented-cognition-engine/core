-- v058: Complete org→product rename at schema level.
--
-- All tables with `org TYPE record<org>` were silently rejecting writes when
-- product_id values (product:platform, etc.) were passed — SurrealDB validates
-- the table name in record<T> strictly. SurrealDB v3 requires REMOVE + DEFINE
-- to change an existing field type (OVERWRITE keyword not yet supported).

REMOVE FIELD org ON decision;
DEFINE FIELD org ON decision TYPE record<product>;

REMOVE FIELD org ON atc_flight;
DEFINE FIELD org ON atc_flight TYPE record<product>;

REMOVE FIELD org ON engine_schedule_override;
DEFINE FIELD org ON engine_schedule_override TYPE record<product>;

REMOVE FIELD org ON agent_config_override;
DEFINE FIELD org ON agent_config_override TYPE record<product>;

REMOVE FIELD org ON capability_lifecycle_track;
DEFINE FIELD org ON capability_lifecycle_track TYPE record<product>;

REMOVE FIELD org ON conductor_rule;
DEFINE FIELD org ON conductor_rule TYPE option<record<product>>;

REMOVE FIELD org ON quality_template;
DEFINE FIELD org ON quality_template TYPE option<record<product>>;

REMOVE FIELD org ON conductor_rule_execution;
DEFINE FIELD org ON conductor_rule_execution TYPE record<product>;

REMOVE FIELD org ON composition_signal;
DEFINE FIELD org ON composition_signal TYPE record<product>;

REMOVE FIELD org ON token_baseline;
DEFINE FIELD org ON token_baseline TYPE record<product>;

REMOVE FIELD org ON session_digest;
DEFINE FIELD org ON session_digest TYPE record<product>;

REMOVE FIELD org ON verification_evidence;
DEFINE FIELD org ON verification_evidence TYPE record<product>;

REMOVE FIELD org ON verification_signal;
DEFINE FIELD org ON verification_signal TYPE record<product>;

REMOVE FIELD org ON evaluator_judgment;
DEFINE FIELD org ON evaluator_judgment TYPE record<product>;

REMOVE FIELD org ON simplicity_audit;
DEFINE FIELD org ON simplicity_audit TYPE record<product>;

REMOVE FIELD org ON resource_lock;
DEFINE FIELD org ON resource_lock TYPE none | record<product>;

UPDATE config_entry SET value = '58' WHERE key = 'schema_version';
