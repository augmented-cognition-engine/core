-- v006: flow control — per-domain intelligence flow configuration
-- Reference: docs/ace-18-complete-schema.md §5 (Configuration)

DEFINE TABLE domain_flow_config SCHEMAFULL;
DEFINE FIELD domain            ON TABLE domain_flow_config TYPE record<domain>;
DEFINE FIELD org               ON TABLE domain_flow_config TYPE record<org>;
DEFINE FIELD default_clearance ON TABLE domain_flow_config TYPE string DEFAULT 'open';
    -- open | domain | restricted | sealed
DEFINE FIELD insight_propagation ON TABLE domain_flow_config TYPE bool DEFAULT true;
DEFINE FIELD consume_org_intelligence ON TABLE domain_flow_config TYPE bool DEFAULT true;
DEFINE FIELD contribute_org_intelligence ON TABLE domain_flow_config TYPE bool DEFAULT true;
DEFINE FIELD review_confidence_threshold ON TABLE domain_flow_config TYPE int DEFAULT 80;
    -- only surface review issues with confidence >= this threshold (from doc 18 §9)
DEFINE INDEX idx_dfc           ON TABLE domain_flow_config FIELDS org, domain UNIQUE;

UPSERT config_entry SET key = 'schema_version', value = '6'
    WHERE key = 'schema_version';
