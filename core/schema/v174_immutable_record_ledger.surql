-- Domain-neutral Core append-only record storage and atomic transaction receipts.

DEFINE TABLE IF NOT EXISTS immutable_record SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE immutable_record TYPE record<product>;
DEFINE FIELD IF NOT EXISTS record_space ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS record_kind ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS record_key ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS transaction_id ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS payload_contract ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS as_of ON TABLE immutable_record TYPE datetime;
DEFINE FIELD IF NOT EXISTS available_at ON TABLE immutable_record TYPE datetime;
DEFINE FIELD IF NOT EXISTS processing_order ON TABLE immutable_record TYPE int;
DEFINE FIELD IF NOT EXISTS payload ON TABLE immutable_record TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE immutable_record TYPE string;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE immutable_record TYPE datetime;
DEFINE INDEX IF NOT EXISTS immutable_record_stable ON TABLE immutable_record
    FIELDS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS immutable_record_scope_key ON TABLE immutable_record
    FIELDS product, record_space, record_kind, record_key UNIQUE;
DEFINE INDEX IF NOT EXISTS immutable_record_as_of ON TABLE immutable_record
    FIELDS product, record_space, record_kind, available_at, stable_id;
DEFINE INDEX IF NOT EXISTS immutable_record_transaction ON TABLE immutable_record
    FIELDS product, transaction_id, processing_order;

DEFINE TABLE IF NOT EXISTS append_only_transaction_receipt SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE append_only_transaction_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE append_only_transaction_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS record_space ON TABLE append_only_transaction_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS transaction_key ON TABLE append_only_transaction_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS transaction_id ON TABLE append_only_transaction_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE append_only_transaction_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS request_hash ON TABLE append_only_transaction_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS material_hash ON TABLE append_only_transaction_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS record_ids ON TABLE append_only_transaction_receipt TYPE array<string>;
DEFINE FIELD IF NOT EXISTS payload ON TABLE append_only_transaction_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS payload_json ON TABLE append_only_transaction_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE append_only_transaction_receipt TYPE datetime;
DEFINE INDEX IF NOT EXISTS append_only_receipt_stable ON TABLE append_only_transaction_receipt
    FIELDS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS append_only_receipt_scope_key ON TABLE append_only_transaction_receipt
    FIELDS product, record_space, transaction_key UNIQUE;
DEFINE INDEX IF NOT EXISTS append_only_receipt_transaction ON TABLE append_only_transaction_receipt
    FIELDS product, transaction_id UNIQUE;

