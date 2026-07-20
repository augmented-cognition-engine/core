-- schema/v103_canvas.surql
-- Decision Canvas v1: canvas_session, canvas_participant, canvas_artifact, canvas_event log.
-- Decisions made on canvas land in existing `decision` table with surface='canvas'.

DEFINE TABLE canvas_session SCHEMALESS;
-- Fields kept lightweight; SCHEMALESS so v1.1 can extend without migration.
-- Recommended fields populated by writes:
--   project_id: string
--   title: string
--   created_at: datetime
--   updated_at: datetime
--   created_by: option<record<user>>
--   ai_participant_id: option<record<canvas_participant>>

DEFINE TABLE canvas_participant SCHEMALESS;
-- Fields:
--   session_id: record<canvas_session>
--   kind: 'ai' | 'human'
--   state: 'idle' | 'watching' | 'drafting' | 'blocked_on_input'
--   updated_at: datetime

DEFINE TABLE canvas_artifact SCHEMALESS;
-- Fields:
--   session_id: record<canvas_session>
--   shape_kind: 'sticky' | 'participant_card' | 'framework_artifact' | 'decision_sticky' | 'lineage_edge' | 'arrow' | 'note'
--   tldraw_shape_id: string  (tldraw shape ID for round-trip)
--   payload: object  (shape-specific data: framework type, citations, lineage refs)
--   x: number
--   y: number
--   created_at: datetime
--   updated_at: datetime
--   author: 'human' | 'ai'

DEFINE TABLE canvas_event SCHEMALESS;
-- Append-only event log. Replayable for retrieval.
-- Fields:
--   session_id: record<canvas_session>
--   event_type: string  (mirrors engine/canvas/event_protocol.py)
--   payload: object
--   surface: 'canvas' | 'cli' | 'ide' | 'transcript' | ...
--   created_at: datetime

-- Indexes for retrieval / lookup.
DEFINE INDEX canvas_session_project ON TABLE canvas_session COLUMNS project_id;
DEFINE INDEX canvas_artifact_session ON TABLE canvas_artifact COLUMNS session_id;
DEFINE INDEX canvas_event_session_time ON TABLE canvas_event COLUMNS session_id, created_at;
DEFINE INDEX canvas_participant_session ON TABLE canvas_participant COLUMNS session_id;

-- Extend `decision` table (defined in v040_connected_graph.surql) with canvas-bridge fields.
-- IMPORTANT: per feedback_surrealdb_schemaless_drift.md, `decision` is SCHEMALESS but
-- v040 already declared DEFINE FIELDs (source, source_session, etc.). When DEFINE FIELDs
-- are present, undeclared fields on CREATE/UPDATE are silently dropped. We MUST DEFINE
-- FIELD any new column we want to persist — bare SCHEMALESS does not save us. ALL FOUR
-- fields below are written by ledger_bridge.py — none can be omitted from the migration.
DEFINE FIELD surface ON TABLE decision TYPE option<string>;
DEFINE FIELD canvas_session_id ON TABLE decision TYPE option<record<canvas_session>>;
DEFINE FIELD cited_artifact_ids ON TABLE decision TYPE option<array<string>>;
DEFINE FIELD framework_kind ON TABLE decision TYPE option<string>;
DEFINE INDEX decision_surface ON TABLE decision COLUMNS surface;
DEFINE INDEX decision_canvas_session ON TABLE decision COLUMNS canvas_session_id;

UPDATE config_entry SET value = '103' WHERE key = 'schema_version';
