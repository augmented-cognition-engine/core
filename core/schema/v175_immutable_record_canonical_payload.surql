-- Preserve opaque record bytes exactly across database object normalization.
-- This is additive for stores that applied v174 before canonical replay landed.

DEFINE FIELD IF NOT EXISTS payload_json ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE append_only_transaction_receipt TYPE string;

