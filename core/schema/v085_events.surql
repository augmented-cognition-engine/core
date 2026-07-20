-- v085: DB-level events for staleness propagation
-- DEFINE EVENT fires DB-side on INSERT/UPDATE — no polling needed.
--
-- observation_created: when a new observation arrives for a file_path,
--   mark any insights that reference that file as stale so ACE re-synthesizes.
--   Insight.source_files (added v083) tracks which files each insight was derived from.
--
-- This closes the write-loop: Edit/Write → ace-post-tool → observation → event →
--   insight.stale_at set → synthesizer reprioritizes that file's insights.

REMOVE EVENT IF EXISTS observation_created ON TABLE observation;
DEFINE EVENT observation_created
    ON TABLE observation
    WHEN $event = "CREATE" AND $value.file_path IS NOT NONE
    THEN {
        LET $fp = $value.file_path;
        UPDATE insight SET
            stale_at    = time::now(),
            stale_reason = string::concat("source file modified: ", $fp)
        WHERE source_files CONTAINS $fp
          AND stale_at IS NONE;
    };

-- Version
UPDATE config_entry SET value = 85 WHERE key = 'schema_version';
