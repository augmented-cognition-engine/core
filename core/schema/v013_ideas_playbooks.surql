-- v013: Ideas + Playbooks
-- Reference: docs/superpowers/specs/2026-03-22-phase5b-ideas-playbooks.md

-- ============================================================
-- IDEA — captured ideas with incubation pipeline
-- ============================================================
DEFINE TABLE idea SCHEMAFULL;
DEFINE FIELD org               ON TABLE idea TYPE record<org>;
DEFINE FIELD workspace         ON TABLE idea TYPE option<record<workspace>>;
DEFINE FIELD user              ON TABLE idea TYPE record<user>;
DEFINE FIELD raw_input         ON TABLE idea TYPE string;
DEFINE FIELD title             ON TABLE idea TYPE option<string>;
DEFINE FIELD status            ON TABLE idea TYPE string DEFAULT 'captured';
    -- captured | qualifying | incubating | ready | active | completed | archived
DEFINE FIELD classification    ON TABLE idea TYPE option<object>;
    -- {domain_path, type, complexity, summary, title}
DEFINE FIELD qualifying_qs     ON TABLE idea TYPE option<array>;
    -- [{q: "...", a: null|"..."}]
DEFINE FIELD research          ON TABLE idea TYPE option<object>;
DEFINE FIELD brief             ON TABLE idea TYPE option<object>;
    -- {what, why, what_we_know, open_questions, approach, effort, risks, first_step}
DEFINE FIELD phases            ON TABLE idea TYPE option<array>;
DEFINE FIELD connections       ON TABLE idea TYPE option<array>;
    -- [{insight_id, content_preview, relevance}]
DEFINE FIELD effort_estimate   ON TABLE idea TYPE option<object>;
DEFINE FIELD priority          ON TABLE idea TYPE option<string>;
    -- low | medium | high | critical
DEFINE FIELD tags              ON TABLE idea TYPE array DEFAULT [];
DEFINE FIELD created_at        ON TABLE idea TYPE datetime DEFAULT time::now();
DEFINE FIELD incubated_at      ON TABLE idea TYPE option<datetime>;
DEFINE FIELD ready_at          ON TABLE idea TYPE option<datetime>;
DEFINE FIELD activated_at      ON TABLE idea TYPE option<datetime>;
DEFINE FIELD archived_at       ON TABLE idea TYPE option<datetime>;
DEFINE INDEX idx_idea_status   ON TABLE idea FIELDS org, user, status;
DEFINE INDEX idx_idea_org      ON TABLE idea FIELDS org, status, created_at;

-- ============================================================
-- PLAYBOOK — saved initiative templates with variables
-- ============================================================
DEFINE TABLE playbook SCHEMAFULL;
DEFINE FIELD org               ON TABLE playbook TYPE record<org>;
DEFINE FIELD name              ON TABLE playbook TYPE string;
DEFINE FIELD description       ON TABLE playbook TYPE string;
DEFINE FIELD domain_path       ON TABLE playbook TYPE string;
DEFINE FIELD milestones        ON TABLE playbook TYPE array DEFAULT [];
    -- [{title, description, done_criteria, requires_approval, work_items: [{title, archetype, mode, domain_path}]}]
DEFINE FIELD variables         ON TABLE playbook TYPE array DEFAULT [];
    -- [{name, type, prompt, default?}]
DEFINE FIELD source_initiatives ON TABLE playbook TYPE option<array>;
    -- initiatives this playbook was derived from (if auto-suggested)
DEFINE FIELD created_by        ON TABLE playbook TYPE record<user>;
DEFINE FIELD times_used        ON TABLE playbook TYPE int DEFAULT 0;
DEFINE FIELD avg_feedback      ON TABLE playbook TYPE float DEFAULT 0.0;
DEFINE FIELD created_at        ON TABLE playbook TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_playbook      ON TABLE playbook FIELDS org, domain_path;

-- Bump schema version
UPSERT config_entry SET key = 'schema_version', value = '13'
    WHERE key = 'schema_version';
