-- schema/v114_forget_log.surql

-- Append-only audit log for the forget erasure primitive (Phase 4).
-- Records that an insight was erased — metadata + content_hash ONLY, never the
-- erased content. update/delete are denied at the engine level so the evidence
-- of an erasure cannot itself be erased. See
-- docs/superpowers/specs/2026-06-15-ace-forget-erasure-primitive-design.md

DEFINE TABLE forget_log SCHEMAFULL
    PERMISSIONS FOR create FULL, FOR select FULL, FOR update NONE, FOR delete NONE;

DEFINE FIELD insight_id    ON forget_log TYPE string;
DEFINE FIELD product       ON forget_log TYPE option<record<product>>;
DEFINE FIELD content_hash  ON forget_log TYPE string;
DEFINE FIELD reason        ON forget_log TYPE string;
DEFINE FIELD actor         ON forget_log TYPE string;
DEFINE FIELD source        ON forget_log TYPE string;
DEFINE FIELD edges_removed ON forget_log TYPE int DEFAULT 0;
DEFINE FIELD deleted_at    ON forget_log TYPE datetime DEFAULT time::now();
DEFINE INDEX forget_log_hash ON forget_log FIELDS content_hash;
