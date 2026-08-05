-- E1-A: additive canonical identity, immutable revision, scoped head, and
-- migration-alias substrate. Runtime package bootstrap is initially adapted
-- through the catalog boundary; later packets populate these records.

DEFINE TABLE IF NOT EXISTS cognition SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition TYPE string;
DEFINE FIELD IF NOT EXISTS cognition_type ON TABLE cognition TYPE string;
DEFINE FIELD IF NOT EXISTS owner ON TABLE cognition TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS stable_key ON TABLE cognition TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE cognition TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS cognition_owner_type_key ON TABLE cognition FIELDS owner, cognition_type, stable_key UNIQUE;

DEFINE TABLE IF NOT EXISTS cognition_revision SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS cognition ON TABLE cognition_revision TYPE record<cognition>;
DEFINE FIELD IF NOT EXISTS body_schema_version ON TABLE cognition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS body ON TABLE cognition_revision TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS dependencies ON TABLE cognition_revision TYPE array<object> DEFAULT [];
DEFINE FIELD IF NOT EXISTS dependencies.* ON TABLE cognition_revision TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS dependencies.*.* ON TABLE cognition_revision TYPE any;
DEFINE FIELD IF NOT EXISTS sources ON TABLE cognition_revision TYPE array<object> DEFAULT [];
DEFINE FIELD IF NOT EXISTS sources.* ON TABLE cognition_revision TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS sources.*.* ON TABLE cognition_revision TYPE any;
DEFINE FIELD IF NOT EXISTS material_hash ON TABLE cognition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS approval_receipt_id ON TABLE cognition_revision TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_revision TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE cognition_revision TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS cognition_revision_material_hash ON TABLE cognition_revision FIELDS material_hash UNIQUE;
DEFINE INDEX IF NOT EXISTS cognition_revision_cognition ON TABLE cognition_revision FIELDS cognition;

DEFINE TABLE IF NOT EXISTS cognition_head SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_head TYPE string;
DEFINE FIELD IF NOT EXISTS cognition ON TABLE cognition_head TYPE record<cognition>;
DEFINE FIELD IF NOT EXISTS scope ON TABLE cognition_head TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS active_revision ON TABLE cognition_head TYPE record<cognition_revision>;
DEFINE FIELD IF NOT EXISTS generation ON TABLE cognition_head TYPE int;
DEFINE FIELD IF NOT EXISTS lifecycle ON TABLE cognition_head TYPE string;
DEFINE FIELD IF NOT EXISTS authority_receipt_id ON TABLE cognition_head TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_head TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS effective_at ON TABLE cognition_head TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS expires_at ON TABLE cognition_head TYPE option<datetime>;
DEFINE INDEX IF NOT EXISTS cognition_head_scope ON TABLE cognition_head FIELDS cognition, scope UNIQUE;

DEFINE TABLE IF NOT EXISTS cognition_activation_event SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS contract_version ON TABLE cognition_activation_event TYPE string;
DEFINE FIELD IF NOT EXISTS cognition ON TABLE cognition_activation_event TYPE record<cognition>;
DEFINE FIELD IF NOT EXISTS scope ON TABLE cognition_activation_event TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS prior_revision ON TABLE cognition_activation_event TYPE option<record<cognition_revision>>;
DEFINE FIELD IF NOT EXISTS active_revision ON TABLE cognition_activation_event TYPE option<record<cognition_revision>>;
DEFINE FIELD IF NOT EXISTS generation ON TABLE cognition_activation_event TYPE int;
DEFINE FIELD IF NOT EXISTS disposition ON TABLE cognition_activation_event TYPE string;
DEFINE FIELD IF NOT EXISTS authority_receipt_id ON TABLE cognition_activation_event TYPE string;
DEFINE FIELD IF NOT EXISTS payload ON TABLE cognition_activation_event TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE cognition_activation_event TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS cognition_activation_generation ON TABLE cognition_activation_event FIELDS cognition, scope, generation UNIQUE;

DEFINE TABLE IF NOT EXISTS cognition_legacy_alias SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS source_kind ON TABLE cognition_legacy_alias TYPE string;
DEFINE FIELD IF NOT EXISTS source_identity ON TABLE cognition_legacy_alias TYPE string;
DEFINE FIELD IF NOT EXISTS source_hash ON TABLE cognition_legacy_alias TYPE string;
DEFINE FIELD IF NOT EXISTS target_cognition ON TABLE cognition_legacy_alias TYPE option<record<cognition>>;
DEFINE FIELD IF NOT EXISTS target_revision ON TABLE cognition_legacy_alias TYPE option<record<cognition_revision>>;
DEFINE FIELD IF NOT EXISTS disposition ON TABLE cognition_legacy_alias TYPE string;
DEFINE FIELD IF NOT EXISTS diagnostics ON TABLE cognition_legacy_alias TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS receipt ON TABLE cognition_legacy_alias TYPE object FLEXIBLE;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE cognition_legacy_alias TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS cognition_legacy_alias_source ON TABLE cognition_legacy_alias FIELDS source_kind, source_identity, source_hash UNIQUE;
