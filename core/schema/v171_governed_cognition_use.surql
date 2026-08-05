-- E1-D: bounded selection and exact material-use receipts.

-- Runtime receipt writes may have created these tables schemaless before an
-- operator applied this migration. OVERWRITE makes the intended contract
-- explicit without deleting existing rows, then the field declarations below
-- validate all subsequent writes.
DEFINE TABLE OVERWRITE cognition_selection_receipt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_selection_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE cognition_selection_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS material_hash ON TABLE cognition_selection_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_selection_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE cognition_selection_receipt TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS cognition_selection_product ON TABLE cognition_selection_receipt FIELDS product, created_at;
DEFINE INDEX IF NOT EXISTS cognition_selection_material ON TABLE cognition_selection_receipt FIELDS material_hash UNIQUE;

DEFINE TABLE OVERWRITE cognition_use_receipt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_use_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE cognition_use_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS material_hash ON TABLE cognition_use_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_use_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE cognition_use_receipt TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS cognition_use_product ON TABLE cognition_use_receipt FIELDS product, created_at;
DEFINE INDEX IF NOT EXISTS cognition_use_material ON TABLE cognition_use_receipt FIELDS material_hash UNIQUE;

-- `task` is intentionally schemaless. Defining FLEXIBLE object fields on a
-- schemaless table is rejected by current SurrealDB, while the table already
-- accepts these additive receipt projections without field declarations.

DEFINE TABLE OVERWRITE cognition_effectiveness_receipt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_effectiveness_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS product ON TABLE cognition_effectiveness_receipt TYPE record<product>;
DEFINE FIELD IF NOT EXISTS revision ON TABLE cognition_effectiveness_receipt TYPE record<cognition_revision>;
DEFINE FIELD IF NOT EXISTS material_hash ON TABLE cognition_effectiveness_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS conclusion ON TABLE cognition_effectiveness_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_effectiveness_receipt TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE cognition_effectiveness_receipt TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS cognition_effectiveness_revision ON TABLE cognition_effectiveness_receipt FIELDS product, revision, created_at;
DEFINE INDEX IF NOT EXISTS cognition_effectiveness_material ON TABLE cognition_effectiveness_receipt FIELDS material_hash UNIQUE;
