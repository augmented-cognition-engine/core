-- TP1B: fenced, product-scoped observation processing leases.
--
-- These fields are additive. Existing pending rows remain claimable. A legacy
-- row stranded in `processing` without lease metadata becomes recoverable only
-- after the bounded orphan threshold enforced by the worker.

DEFINE FIELD IF NOT EXISTS processing_lease_id ON observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS processing_lease_owner ON observation TYPE option<string>;
DEFINE FIELD IF NOT EXISTS processing_lease_generation ON observation TYPE option<int>;
DEFINE FIELD IF NOT EXISTS processing_lease_acquired_at ON observation TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS processing_lease_heartbeat_at ON observation TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS processing_lease_expires_at ON observation TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS processing_lease_recovered ON observation TYPE option<bool>;
DEFINE FIELD IF NOT EXISTS processing_lease_prior_state ON observation TYPE option<string>;

DEFINE INDEX IF NOT EXISTS idx_observation_lease_claim ON observation
    FIELDS product, status, processing_state, next_retry_at,
    processing_lease_expires_at, processing_started_at, created_at;
DEFINE INDEX IF NOT EXISTS idx_observation_lease_owner ON observation
    FIELDS product, processing_lease_owner, processing_lease_expires_at;
