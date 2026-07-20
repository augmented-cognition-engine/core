-- v004: document storage for Portal
-- Reference: docs/ace-18-complete-schema.md §4 (Operational)

DEFINE TABLE document SCHEMAFULL;
DEFINE FIELD org              ON TABLE document TYPE record<org>;
DEFINE FIELD workspace        ON TABLE document TYPE option<record<workspace>>;
DEFINE FIELD title            ON TABLE document TYPE string;
DEFINE FIELD content          ON TABLE document TYPE string;
DEFINE FIELD doc_type         ON TABLE document TYPE string;
    -- architecture | convention | roadmap | runbook | meeting_notes | guide | other
DEFINE FIELD domain           ON TABLE document TYPE option<record<domain>>;
DEFINE FIELD tags             ON TABLE document TYPE array DEFAULT [];
DEFINE FIELD version          ON TABLE document TYPE int DEFAULT 1;
DEFINE FIELD created_by       ON TABLE document TYPE record<user>;
DEFINE FIELD updated_by       ON TABLE document TYPE option<record<user>>;
DEFINE FIELD created_at       ON TABLE document TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at       ON TABLE document TYPE datetime DEFAULT time::now();
DEFINE FIELD last_ingested    ON TABLE document TYPE option<datetime>;
DEFINE INDEX idx_doc_org      ON TABLE document FIELDS org, doc_type;
DEFINE INDEX idx_doc_domain   ON TABLE document FIELDS org, domain;

UPSERT config_entry SET key = 'schema_version', value = '4'
    WHERE key = 'schema_version';
