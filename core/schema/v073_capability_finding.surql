-- v073: capability_finding table — persists static analysis findings from E2
-- Links findings to capabilities via graph_file → realizes → capability

DEFINE TABLE capability_finding SCHEMALESS;

DEFINE FIELD product ON capability_finding TYPE record<product>;
DEFINE FIELD capability ON capability_finding TYPE option<record<capability>>;
DEFINE FIELD discipline ON capability_finding TYPE string;
DEFINE FIELD severity ON capability_finding TYPE string;
DEFINE FIELD file ON capability_finding TYPE string;
DEFINE FIELD line ON capability_finding TYPE option<int>;
DEFINE FIELD col ON capability_finding TYPE option<int>;
DEFINE FIELD message ON capability_finding TYPE string;
DEFINE FIELD rule_id ON capability_finding TYPE option<string>;
DEFINE FIELD fix_command ON capability_finding TYPE option<string>;
DEFINE FIELD tool ON capability_finding TYPE string;
DEFINE FIELD scan_id ON capability_finding TYPE string;
DEFINE FIELD created_at ON capability_finding TYPE datetime;
DEFINE FIELD resolved_at ON capability_finding TYPE option<datetime>;

DEFINE INDEX cf_product ON capability_finding FIELDS product;
DEFINE INDEX cf_discipline ON capability_finding FIELDS product, discipline;
DEFINE INDEX cf_scan ON capability_finding FIELDS scan_id;
DEFINE INDEX cf_file ON capability_finding FIELDS product, file;
