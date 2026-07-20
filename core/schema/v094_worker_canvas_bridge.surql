-- v094: Worker canvas bridge — persistent signal log for closed-loop

DEFINE TABLE worker_signal SCHEMALESS;
DEFINE FIELD product       ON worker_signal TYPE record<product>;
DEFINE FIELD kind          ON worker_signal TYPE string;
DEFINE FIELD event_type    ON worker_signal TYPE string;
DEFINE FIELD payload       ON worker_signal TYPE object;
DEFINE FIELD confidence    ON worker_signal TYPE float;
DEFINE FIELD emitted_at    ON worker_signal TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_ws_product_kind ON worker_signal FIELDS product, kind, emitted_at;

UPDATE config_entry SET value = '94' WHERE key = 'schema_version';
