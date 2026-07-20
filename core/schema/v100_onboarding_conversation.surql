-- v100: Onboarding conversation state for the partner-voice opener (Cohort A item #8)
--
-- Tracks an in-progress onboarding conversation so partial answers survive
-- refresh. Conversations are short-lived (single user session, typically ~60s)
-- but the persistence guarantees AC4: refresh mid-flow resumes from the next
-- unanswered question without losing prior answers.

DEFINE TABLE onboarding_conversation SCHEMALESS;
DEFINE FIELD started_at      ON onboarding_conversation TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at    ON onboarding_conversation TYPE option<datetime>;
DEFINE FIELD created_by      ON onboarding_conversation TYPE option<string>;
DEFINE FIELD answers         ON onboarding_conversation TYPE array DEFAULT [];
DEFINE FIELD product_id      ON onboarding_conversation TYPE option<record<product>>;
DEFINE INDEX idx_oc_started ON onboarding_conversation FIELDS started_at;
DEFINE INDEX idx_oc_user    ON onboarding_conversation FIELDS created_by, started_at;

UPDATE config_entry SET value = '100' WHERE key = 'schema_version';
