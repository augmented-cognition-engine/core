-- v056: Index on project.repo_path for fast product auto-detection.
-- Auto-detection queries: SELECT product FROM project WHERE repo_path = $git_root
-- This index makes that O(1) instead of a full table scan.

DEFINE INDEX idx_proj_repo_path ON project FIELDS repo_path;

UPDATE config_entry SET value = '56' WHERE key = 'schema_version';
