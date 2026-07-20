-- schema/v127_action_outcome_profile.surql
-- Depth learning loop: record the WorkProfile + assembled pipeline each build chose, so the
-- depth_scorer can learn which profile-classes keep failing verify. Additive + optional ->
-- backward-compatible with existing action_outcome rows (no bare required field; v126 lesson).
DEFINE FIELD profile_scope        ON action_outcome TYPE option<string>;
DEFINE FIELD profile_novelty      ON action_outcome TYPE option<string>;
DEFINE FIELD profile_risk         ON action_outcome TYPE option<string>;
DEFINE FIELD profile_verify_depth ON action_outcome TYPE option<string>;
DEFINE FIELD profile_task_type    ON action_outcome TYPE option<string>;
DEFINE FIELD pipeline             ON action_outcome TYPE option<array<string>>;
-- product leads (the score_depth query filters on it) so the index stays selective when multi-product.
DEFINE INDEX idx_ao_learn ON action_outcome FIELDS product, arm_domain, profile_novelty, profile_risk, created_at;
