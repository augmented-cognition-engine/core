-- schema/v009_execution.surql
-- Phase 4a: Temporal read indexes for context assembly

-- Optimize observation reads by domain hint + recency (for deliberative/exploratory modes)
DEFINE INDEX idx_obs_temporal ON TABLE observation
    FIELDS org, domain_hint, synthesized, created_at;

-- Optimize memory reads by recency (for exploratory mode)
DEFINE INDEX idx_mem_temporal ON TABLE memory
    FIELDS org, processed, created_at;
