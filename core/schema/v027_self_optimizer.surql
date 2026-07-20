-- v027_self_optimizer.surql
-- Self-optimizer: proposals, specialty affinities, state tracking

DEFINE TABLE self_optimizer_state SCHEMAFULL;
DEFINE FIELD org         ON TABLE self_optimizer_state TYPE record<org>;
DEFINE FIELD counter     ON TABLE self_optimizer_state TYPE int DEFAULT 0;
DEFINE FIELD threshold   ON TABLE self_optimizer_state TYPE int DEFAULT 10;
DEFINE FIELD min_tasks   ON TABLE self_optimizer_state TYPE int DEFAULT 3;
DEFINE FIELD min_combined_score ON TABLE self_optimizer_state TYPE float DEFAULT 0.25;
DEFINE FIELD last_run    ON TABLE self_optimizer_state TYPE option<datetime>;
DEFINE FIELD updated_at  ON TABLE self_optimizer_state TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_so_org  ON TABLE self_optimizer_state FIELDS org UNIQUE;

DEFINE TABLE self_optimizer_proposal SCHEMAFULL;
DEFINE FIELD org            ON TABLE self_optimizer_proposal TYPE record<org>;
DEFINE FIELD type           ON TABLE self_optimizer_proposal TYPE string;
DEFINE FIELD status         ON TABLE self_optimizer_proposal TYPE string DEFAULT 'proposed';
DEFINE FIELD name           ON TABLE self_optimizer_proposal TYPE string;
DEFINE FIELD description    ON TABLE self_optimizer_proposal TYPE string DEFAULT '';
DEFINE FIELD draft          ON TABLE self_optimizer_proposal TYPE option<object>;
DEFINE FIELD evidence       ON TABLE self_optimizer_proposal TYPE object DEFAULT {};
DEFINE FIELD source_tasks   ON TABLE self_optimizer_proposal TYPE array<string> DEFAULT [];
DEFINE FIELD source_insights ON TABLE self_optimizer_proposal TYPE array<string> DEFAULT [];
DEFINE FIELD created_at     ON TABLE self_optimizer_proposal TYPE datetime DEFAULT time::now();
DEFINE FIELD reviewed_at    ON TABLE self_optimizer_proposal TYPE option<datetime>;
DEFINE INDEX idx_prop_org   ON TABLE self_optimizer_proposal FIELDS org, status, type;

DEFINE TABLE specialty_affinity SCHEMAFULL;
DEFINE FIELD specialty_a    ON TABLE specialty_affinity TYPE record<specialty>;
DEFINE FIELD specialty_b    ON TABLE specialty_affinity TYPE record<specialty>;
DEFINE FIELD org            ON TABLE specialty_affinity TYPE record<org>;
DEFINE FIELD strength       ON TABLE specialty_affinity TYPE float DEFAULT 0.5;
DEFINE FIELD co_occurrence  ON TABLE specialty_affinity TYPE int DEFAULT 0;
DEFINE FIELD avg_utilization ON TABLE specialty_affinity TYPE float DEFAULT 0.0;
DEFINE FIELD avg_feedback   ON TABLE specialty_affinity TYPE float DEFAULT 0.0;
DEFINE FIELD created_at     ON TABLE specialty_affinity TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at     ON TABLE specialty_affinity TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_aff_pair   ON TABLE specialty_affinity FIELDS specialty_a, specialty_b, org UNIQUE;
DEFINE INDEX idx_aff_org    ON TABLE specialty_affinity FIELDS org;

DEFINE FIELD specialties_loaded ON TABLE task TYPE option<array<string>>;

UPSERT config_entry SET value = '27' WHERE key = 'schema_version';
