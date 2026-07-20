-- v045: ATC Flight Registry
-- Foundation for Air Traffic Control execution model.
-- Every change set (agent task, initiative, human PR) is a "flight"
-- that occupies capabilities and gets sequenced by ATC.

DEFINE TABLE atc_flight SCHEMALESS;
DEFINE FIELD org ON atc_flight TYPE record<org>;
DEFINE FIELD source ON atc_flight TYPE string;
DEFINE FIELD source_id ON atc_flight TYPE string;
DEFINE FIELD title ON atc_flight TYPE option<string>;
DEFINE FIELD capabilities ON atc_flight TYPE option<array>;
DEFINE FIELD files_predicted ON atc_flight TYPE option<array>;
DEFINE FIELD files_actual ON atc_flight TYPE option<array>;
DEFINE FIELD status ON atc_flight TYPE string DEFAULT 'planning';
DEFINE FIELD priority ON atc_flight TYPE int DEFAULT 50;
DEFINE FIELD blocked_by ON atc_flight TYPE option<record<atc_flight>>;
DEFINE FIELD worktree_path ON atc_flight TYPE option<string>;
DEFINE FIELD target_branch ON atc_flight TYPE string DEFAULT 'main';
DEFINE FIELD plan_created_at ON atc_flight TYPE option<datetime>;
DEFINE FIELD cleared_at ON atc_flight TYPE option<datetime>;
DEFINE FIELD landed_at ON atc_flight TYPE option<datetime>;
DEFINE FIELD created_at ON atc_flight TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON atc_flight TYPE datetime DEFAULT time::now();
