-- I1 closeout: additive supplier provenance and correction expiry.
-- Existing records remain explicit partial/degraded projections; no facts are
-- reconstructed and no history is deleted.

DEFINE FIELD IF NOT EXISTS originating_actor_class ON TABLE decision TYPE option<string>;
DEFINE FIELD IF NOT EXISTS expires_at ON TABLE observation TYPE option<datetime>;
