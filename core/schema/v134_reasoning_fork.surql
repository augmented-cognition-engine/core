-- schema/v134_reasoning_fork.surql
-- Forkable foresight: cached fork-and-compare results, keyed by (run_id, checkpoint_seq), short TTL.
-- fork_and_compare runs N MultiPhaseExecutor passes (expensive), so a re-fork of the same run +
-- checkpoint within the TTL returns the cached comparison instead of re-reasoning — the same caching
-- contract as rollout_cache (v105). SCHEMALESS: the cached `result` carries nested objects
-- (best / original / forks, each a ForkBranch).
DEFINE TABLE reasoning_fork SCHEMALESS;
