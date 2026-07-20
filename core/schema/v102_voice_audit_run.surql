-- v102: Voice consistency audit — voice_audit_run table for periodic + manual audit results

DEFINE TABLE voice_audit_run SCHEMALESS;
DEFINE FIELD ran_at         ON voice_audit_run TYPE datetime DEFAULT time::now();
DEFINE FIELD product        ON voice_audit_run TYPE option<record<product>>;
DEFINE FIELD surface_scores ON voice_audit_run TYPE object;
DEFINE FIELD violations     ON voice_audit_run TYPE array DEFAULT [];
DEFINE FIELD overall_score  ON voice_audit_run TYPE float;
DEFINE FIELD trigger        ON voice_audit_run TYPE string DEFAULT 'sweeper';

DEFINE INDEX idx_var_ran      ON voice_audit_run FIELDS ran_at;
DEFINE INDEX idx_var_product  ON voice_audit_run FIELDS product, ran_at;

UPDATE config_entry SET value = '102' WHERE key = 'schema_version';
