-- schema/v106_orchestration_channel.surql
-- A.7 Canvas Orchestration Channel: execution tree persistence + conversation log.

-- Run execution tree events (ephemeral, 30-day TTL via app-level cleanup)
DEFINE TABLE run_event SCHEMALESS;
-- Fields written by EventBus.emit() when persist_events=True:
--   run_id:     string   — UUID for the execution tree root
--   task_id:    string   — UUID for this specific node
--   parent_id:  string?  — null for root events, otherwise parent task_id
--   ts:         datetime — event timestamp
--   type:       string   — discriminator (run_start, block_start, claude_call_done, etc.)
--   payload:    object   — type-specific fields

DEFINE INDEX run_event_run ON TABLE run_event COLUMNS run_id;
DEFINE INDEX run_event_task ON TABLE run_event COLUMNS task_id;

-- Flat session conversation log (not a memory replacement for the graph)
DEFINE TABLE conversation_message SCHEMALESS;
-- session_id, role ('user'|'ace'), content, run_id, created_at

DEFINE INDEX conv_msg_session ON TABLE conversation_message COLUMNS session_id, created_at;

-- Turn-level linking: which user message ↔ which synthesis ↔ which decisions
DEFINE TABLE conversation_turn SCHEMALESS;
-- session_id, run_id, user_message_id, synthesis_message_id,
-- decision_ids[], prediction_ids[], created_at

DEFINE INDEX conv_turn_session ON TABLE conversation_turn COLUMNS session_id;
DEFINE INDEX conv_turn_run ON TABLE conversation_turn COLUMNS run_id;

UPDATE config_entry SET value = '106' WHERE key = 'schema_version';
