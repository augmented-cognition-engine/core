-- schema/v112_insight_needs_embedding.surql

-- Phase 1 (A+) atomic single-substrate memory.
-- The `embedding` field already exists (v062). This adds a degraded-mode flag:
-- when the embedder is unavailable at capture time, the insight is written
-- atomically with embedding = NONE and needs_embedding = true, and a reconciler
-- backfills the vector later. NULL/absent means "not in degraded mode".
-- See docs/superpowers/specs/2026-06-13-ace-atomic-single-substrate-memory-design.md

DEFINE FIELD needs_embedding ON TABLE insight TYPE option<bool>;
DEFINE INDEX insight_needs_embedding ON TABLE insight FIELDS needs_embedding;
