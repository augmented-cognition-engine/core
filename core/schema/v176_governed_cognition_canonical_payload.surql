-- Preserve governed-cognition contract bytes exactly across SurrealDB object
-- normalization. Object projections remain queryable; canonical JSON owns replay.

DEFINE FIELD IF NOT EXISTS payload_json ON TABLE cognition TYPE string;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE cognition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE cognition_head TYPE string;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE cognition_proposal TYPE string;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE cognition_review_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE cognition_selection_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE cognition_use_receipt TYPE string;
