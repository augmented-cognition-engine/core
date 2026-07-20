-- schema/v110_cost_aware_reasoning.surql

-- Adds cost-aware reasoning fields to composition_signal (Phase A spec
-- docs/superpowers/specs/2026-05-25-ace-cost-aware-reasoning-design.md).
--
-- All fields are option<...> — backward compatible. Existing rows remain
-- valid; the composition_signal_hook will populate the new fields going
-- forward for legacy-path runs. Deep-committee runs remain invisible to
-- composition_signal until Phase B.

DEFINE FIELD model_used                     ON composition_signal TYPE option<string>;
DEFINE FIELD budget_estimated               ON composition_signal TYPE option<int>;
DEFINE FIELD budget_used                    ON composition_signal TYPE option<int>;
DEFINE FIELD call_budget_estimated          ON composition_signal TYPE option<int>;
DEFINE FIELD call_count_used                ON composition_signal TYPE option<int>;
DEFINE FIELD cost_usd                       ON composition_signal TYPE option<float>;
DEFINE FIELD estimated_alternative_cost_usd ON composition_signal TYPE option<float>;
DEFINE FIELD overthinking_flag              ON composition_signal TYPE option<bool>;
