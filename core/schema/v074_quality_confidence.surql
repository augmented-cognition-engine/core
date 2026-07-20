-- v074: D5 — add confidence and evidence_count to capability_quality
-- DEFAULT ensures existing rows remain valid without re-running gap analyzer

DEFINE FIELD confidence ON TABLE capability_quality TYPE float DEFAULT 0.5;
DEFINE FIELD evidence_count ON TABLE capability_quality TYPE int DEFAULT 0;
