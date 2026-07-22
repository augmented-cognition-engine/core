-- F1: link observed comparator evidence to the frozen plan it followed.
-- Alignment is diagnostic provenance. It never turns a plan into evidence or independently
-- establishes causality.

DEFINE FIELD IF NOT EXISTS comparator_plan_id ON TABLE observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS comparator_alignment_state ON TABLE observation TYPE option<string>;

DEFINE INDEX IF NOT EXISTS observation_product_comparator_plan_observed ON TABLE observation
    FIELDS product, comparator_plan_id, comparator_alignment_state, observed_at;

UPDATE config_entry SET value = '153' WHERE key = 'schema_version';
