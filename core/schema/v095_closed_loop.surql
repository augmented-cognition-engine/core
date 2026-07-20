-- v095: Closed-loop learning — outcome observations + effectiveness ledger

DEFINE TABLE outcome_observation SCHEMALESS;
DEFINE FIELD product            ON outcome_observation TYPE record<product>;
DEFINE FIELD emission_id        ON outcome_observation TYPE string;
DEFINE FIELD emission_kind      ON outcome_observation TYPE string;
DEFINE FIELD emission_topic     ON outcome_observation TYPE string;
DEFINE FIELD pillar             ON outcome_observation TYPE option<string>;
DEFINE FIELD discipline         ON outcome_observation TYPE option<string>;
DEFINE FIELD emitted_at         ON outcome_observation TYPE datetime;
DEFINE FIELD outcome_label      ON outcome_observation TYPE string;
DEFINE FIELD outcome_at         ON outcome_observation TYPE option<datetime>;
DEFINE FIELD action_evidence    ON outcome_observation TYPE option<object>;
DEFINE FIELD window_expires_at  ON outcome_observation TYPE datetime;
DEFINE INDEX idx_oo_product_pillar  ON outcome_observation FIELDS product, pillar, emitted_at;
DEFINE INDEX idx_oo_outcome_label   ON outcome_observation FIELDS product, outcome_label, outcome_at;
DEFINE INDEX idx_oo_window_expires  ON outcome_observation FIELDS product, outcome_label, window_expires_at;
DEFINE INDEX idx_oo_idempotency     ON outcome_observation FIELDS product, emission_kind, emission_id UNIQUE;

DEFINE TABLE effectiveness_score SCHEMALESS;
DEFINE FIELD product       ON effectiveness_score TYPE record<product>;
DEFINE FIELD pillar        ON effectiveness_score TYPE string;
DEFINE FIELD discipline    ON effectiveness_score TYPE string;
DEFINE FIELD n_emissions   ON effectiveness_score TYPE int;
DEFINE FIELD n_acted_on    ON effectiveness_score TYPE int;
DEFINE FIELD n_ignored     ON effectiveness_score TYPE int;
DEFINE FIELD n_rejected    ON effectiveness_score TYPE int;
DEFINE FIELD raw_rate      ON effectiveness_score TYPE float;
DEFINE FIELD smoothed_rate ON effectiveness_score TYPE float;
DEFINE FIELD confidence    ON effectiveness_score TYPE float;
DEFINE FIELD computed_at   ON effectiveness_score TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_es_product_key ON effectiveness_score FIELDS product, pillar, discipline, computed_at;

UPDATE config_entry SET value = '95' WHERE key = 'schema_version';
