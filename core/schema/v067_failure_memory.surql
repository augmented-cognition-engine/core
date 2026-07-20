-- v067: failure_memory — Reflexion-style failure accumulation
-- Stores VerificationGate gaps from failed/partial verifications.
-- Read by load_intelligence() to surface failure modes as context in future tasks.

DEFINE TABLE failure_memory SCHEMALESS;

-- Fields written by engine/orchestration/executor.py after verification:
-- product: record<product>
-- discipline: string (e.g. "coding", "security")
-- task_summary: string (first 200 chars of task description — human-readable)
-- gaps: array<string> (from VerificationGate.gaps — specific failure modes)
-- verdict: string ("gaps_found" | "failed")
-- created_at: datetime

DEFINE INDEX idx_failure_memory_product_discipline
  ON TABLE failure_memory
  FIELDS product, discipline;

-- ─── Version bump ─────────────────────────────────────────────────────────────

UPDATE config_entry SET value = '67' WHERE key = 'schema_version';
