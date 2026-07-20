-- v038_drop_graph_shadows.surql
-- Drop 9 graph_* shadow tables + graph_agent (replaced by agent_execution in v037)

REMOVE TABLE IF EXISTS graph_initiative;
REMOVE TABLE IF EXISTS graph_task;
REMOVE TABLE IF EXISTS graph_idea;
REMOVE TABLE IF EXISTS graph_document;
REMOVE TABLE IF EXISTS graph_user;
REMOVE TABLE IF EXISTS graph_specialty;
REMOVE TABLE IF EXISTS graph_config;
REMOVE TABLE IF EXISTS graph_insight;
REMOVE TABLE IF EXISTS graph_instance;
REMOVE TABLE IF EXISTS graph_agent;

UPDATE config_entry:schema_version SET value = '038';
