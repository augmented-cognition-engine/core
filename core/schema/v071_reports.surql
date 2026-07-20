-- v071: add report table for consulting deliverables
DEFINE TABLE report SCHEMALESS;
DEFINE INDEX idx_report_product ON TABLE report FIELDS product;
DEFINE INDEX idx_report_product_type ON TABLE report FIELDS product, type;

UPDATE config_entry SET value = '71' WHERE key = 'schema_version';
