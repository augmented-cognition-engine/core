-- schema/v138_reeval_rederivation.surql
-- Shadow re-derivation proposal fields on the metabolism's re-evaluation queue.
--
-- When a belief's canvas ground shifts, rederive_belief() asks the LLM "does the
-- evidence still support this belief, and at what confidence?" — and records the
-- answer HERE, on the reeval_request, WITHOUT touching the belief's live confidence.
-- Shadow mode (the codebase's "v1.0 shadow mode" pattern): propose, never apply, so
-- a re-derivation can never corrupt the graph's confidence. Whether/how proposals
-- get applied is governed later (11-SUBSTRATE §5).
--
-- All option<> + IF NOT EXISTS (idempotent, legacy rows survive).

DEFINE FIELD IF NOT EXISTS proposed_confidence    ON reeval_request TYPE option<float>;
DEFINE FIELD IF NOT EXISTS rederivation_rationale ON reeval_request TYPE option<string>;
DEFINE FIELD IF NOT EXISTS still_supported        ON reeval_request TYPE option<bool>;
DEFINE FIELD IF NOT EXISTS rederived_at           ON reeval_request TYPE option<datetime>;

UPSERT config_entry SET key = 'schema_version', value = '138' WHERE key = 'schema_version';
