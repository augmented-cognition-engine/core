-- v005: synaptic graph — connections between subdomains
-- Reference: docs/ace-18-complete-schema.md §2 (Intelligence)
-- Spec: docs/superpowers/specs/2026-03-21-phase2a-synaptic-graph.md

DEFINE TABLE synapse SCHEMAFULL;
DEFINE FIELD in                ON TABLE synapse TYPE record;
DEFINE FIELD out               ON TABLE synapse TYPE record;
DEFINE FIELD org               ON TABLE synapse TYPE record<org>;
DEFINE FIELD strength          ON TABLE synapse TYPE float DEFAULT 0.0;
DEFINE FIELD direction         ON TABLE synapse TYPE string;
    -- bidirectional | one_way
DEFINE FIELD interface_type    ON TABLE synapse TYPE option<string>;
    -- produces | consumes | reviews | informs | blocks
DEFINE FIELD origin            ON TABLE synapse TYPE string;
    -- structural | observed | declared
DEFINE FIELD co_occurrence     ON TABLE synapse TYPE int DEFAULT 0;
DEFINE FIELD confirmed         ON TABLE synapse TYPE bool DEFAULT false;
DEFINE FIELD confirmed_by      ON TABLE synapse TYPE option<record<user>>;
DEFINE FIELD dismissed_at      ON TABLE synapse TYPE option<datetime>;
DEFINE FIELD dismiss_threshold ON TABLE synapse TYPE int DEFAULT 10;
DEFINE FIELD proposal_evidence ON TABLE synapse TYPE option<object>;
DEFINE FIELD last_fired        ON TABLE synapse TYPE option<datetime>;
DEFINE FIELD created_at        ON TABLE synapse TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_syn_org       ON TABLE synapse FIELDS org;
DEFINE INDEX idx_syn_nodes     ON TABLE synapse FIELDS in, out;
DEFINE INDEX idx_syn_confirmed ON TABLE synapse FIELDS org, confirmed;

UPSERT config_entry SET key = 'schema_version', value = '5'
    WHERE key = 'schema_version';
