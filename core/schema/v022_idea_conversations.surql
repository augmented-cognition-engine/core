-- schema/v022_idea_conversations.surql
-- Add source_idea provenance to task table for idea-to-task promotion.
-- Spec: docs/superpowers/specs/2026-03-24-conversational-idea-development.md

DEFINE FIELD IF NOT EXISTS source_idea ON TABLE task TYPE option<record<idea>>;

-- Schema version
UPDATE config_entry SET value = '22' WHERE key = 'schema_version';
