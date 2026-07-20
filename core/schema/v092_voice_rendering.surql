-- v092: Voice rendering substrate (per docs/superpowers/specs/2026-04-29-voice-rendering-design.md)

-- briefing.format and briefing.payload_ref are additive on SCHEMALESS — no DEFINE FIELD needed.
-- Documenting them here so future readers of schema know what to expect:
--   briefing.format       string  -- 'partner_voice_v1' for new ones; absent/legacy for old
--   briefing.payload_ref  record<briefing_payload>?

-- Stored payload alongside each rendered briefing — supports v2 replay.
DEFINE TABLE briefing_payload SCHEMALESS;
DEFINE FIELD product      ON briefing_payload TYPE record<product>;
DEFINE FIELD payload_json ON briefing_payload TYPE object;
DEFINE FIELD computed_at  ON briefing_payload TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_bp_product ON briefing_payload FIELDS product, computed_at;

-- Drift detector state: tracks last blocked-fraction band per product so the
-- detector only emits canvas.drift.crossed when the band actually changes.
DEFINE TABLE voice_drift_state SCHEMALESS;
DEFINE FIELD product           ON voice_drift_state TYPE record<product>;
DEFINE FIELD last_blocked_frac ON voice_drift_state TYPE float;
DEFINE FIELD last_computed_at  ON voice_drift_state TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_vds_product ON voice_drift_state FIELDS product;

-- Recommendation-shift detector state: tracks current top-1 (pillar, discipline, score)
-- per product so the detector only emits canvas.recommendation.shifted on swap or
-- score-shift > 0.05.
DEFINE TABLE voice_top_recommendation_state SCHEMALESS;
DEFINE FIELD product             ON voice_top_recommendation_state TYPE record<product>;
DEFINE FIELD top_pillar          ON voice_top_recommendation_state TYPE string;
DEFINE FIELD top_discipline      ON voice_top_recommendation_state TYPE string;
DEFINE FIELD top_rank_score      ON voice_top_recommendation_state TYPE float;
DEFINE FIELD updated_at          ON voice_top_recommendation_state TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_vtrs_product ON voice_top_recommendation_state FIELDS product;

UPDATE config_entry SET value = '92' WHERE key = 'schema_version';
