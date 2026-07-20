-- Routing feedback loop: classifier corrections + outcome quality signals

-- Explicit routing corrections: when a task was misrouted, record what it
-- should have been. Consumed by classify_task() as dynamic few-shot examples.
DEFINE TABLE routing_correction SCHEMALESS;
DEFINE INDEX idx_routing_correction_product
  ON TABLE routing_correction
  FIELDS product;

-- Index for fast recent-corrections query in classify_task()
DEFINE INDEX idx_routing_correction_product_created
  ON TABLE routing_correction
  FIELDS product, created_at;

UPDATE config_entry SET value = '69' WHERE key = 'schema_version';
