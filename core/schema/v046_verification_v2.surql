-- v046: Verification V2 — behavioral evidence, evaluator honesty, simplicity audit
-- Closes three gaps from Anthropic's harness design article:
-- 1. Behavioral checks produce runtime evidence before LLM judgment
-- 2. Evaluator honesty tracks pre-commitment vs final verdict (anti-sycophancy)
-- 3. Simplicity audit detects dormant/unjustified architectural complexity

-- ─────────────────────────────────────────────
-- Gap 1: Behavioral verification evidence
-- ─────────────────────────────────────────────

DEFINE TABLE verification_evidence SCHEMAFULL;
DEFINE FIELD org ON verification_evidence TYPE record<org>;
DEFINE FIELD spec_id ON verification_evidence TYPE record<agent_spec>;
DEFINE FIELD criterion_index ON verification_evidence TYPE int;
DEFINE FIELD check_type ON verification_evidence TYPE string
  ASSERT $value IN ['test_execution', 'code_inspection', 'integration_validation'];
DEFINE FIELD status ON verification_evidence TYPE string
  ASSERT $value IN ['passed', 'failed', 'skipped', 'error'];
DEFINE FIELD details ON verification_evidence TYPE object;
DEFINE FIELD details.* ON verification_evidence TYPE any;
DEFINE FIELD duration_ms ON verification_evidence TYPE int DEFAULT 0;
DEFINE FIELD created_at ON verification_evidence TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_ve_spec ON verification_evidence FIELDS spec_id, criterion_index;
DEFINE INDEX idx_ve_org ON verification_evidence FIELDS org, created_at;

-- Aggregated signal per spec verification run (parallel to composition_signal)
DEFINE TABLE verification_signal SCHEMAFULL;
DEFINE FIELD org ON verification_signal TYPE record<org>;
DEFINE FIELD spec_id ON verification_signal TYPE record<agent_spec>;
DEFINE FIELD checks_run ON verification_signal TYPE int DEFAULT 0;
DEFINE FIELD checks_passed ON verification_signal TYPE int DEFAULT 0;
DEFINE FIELD checks_failed ON verification_signal TYPE int DEFAULT 0;
DEFINE FIELD evidence_aligned ON verification_signal TYPE bool DEFAULT true;
DEFINE FIELD overall_verdict ON verification_signal TYPE string DEFAULT 'unknown';
DEFINE FIELD created_at ON verification_signal TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_vs_spec ON verification_signal FIELDS spec_id UNIQUE;
DEFINE INDEX idx_vs_org ON verification_signal FIELDS org, created_at;

-- ─────────────────────────────────────────────
-- Gap 2: Evaluator honesty tracking
-- ─────────────────────────────────────────────

DEFINE TABLE evaluator_judgment SCHEMAFULL;
DEFINE FIELD org ON evaluator_judgment TYPE record<org>;
DEFINE FIELD spec_id ON evaluator_judgment TYPE record<agent_spec>;
DEFINE FIELD criterion_index ON evaluator_judgment TYPE int;
DEFINE FIELD pre_commitment ON evaluator_judgment TYPE string;
DEFINE FIELD final_verdict ON evaluator_judgment TYPE string;
DEFINE FIELD flipped ON evaluator_judgment TYPE bool DEFAULT false;
DEFINE FIELD evidence_aligned ON evaluator_judgment TYPE bool DEFAULT true;
DEFINE FIELD overridden ON evaluator_judgment TYPE bool DEFAULT false;
DEFINE FIELD override_reason ON evaluator_judgment TYPE option<string>;
DEFINE FIELD behavioral_evidence_summary ON evaluator_judgment TYPE object;
DEFINE FIELD behavioral_evidence_summary.* ON evaluator_judgment TYPE any;
DEFINE FIELD created_at ON evaluator_judgment TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_ej_spec ON evaluator_judgment FIELDS spec_id, criterion_index;
DEFINE INDEX idx_ej_org ON evaluator_judgment FIELDS org, created_at;

-- ─────────────────────────────────────────────
-- Gap 3: Simplicity audit results
-- ─────────────────────────────────────────────

DEFINE TABLE simplicity_audit SCHEMAFULL;
DEFINE FIELD org ON simplicity_audit TYPE record<org>;
DEFINE FIELD dormant_components ON simplicity_audit TYPE array;
DEFINE FIELD dormant_components.* ON simplicity_audit TYPE any;
DEFINE FIELD low_value_components ON simplicity_audit TYPE array;
DEFINE FIELD low_value_components.* ON simplicity_audit TYPE any;
DEFINE FIELD justified_components ON simplicity_audit TYPE array;
DEFINE FIELD justified_components.* ON simplicity_audit TYPE any;
DEFINE FIELD recommendations ON simplicity_audit TYPE array;
DEFINE FIELD recommendations.* ON simplicity_audit TYPE any;
DEFINE FIELD complexity_score ON simplicity_audit TYPE float DEFAULT 0.0;
DEFINE FIELD created_at ON simplicity_audit TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_sa_org ON simplicity_audit FIELDS org, created_at;

-- Bump schema version
UPSERT config_entry SET key = 'schema_version', value = '46'
  WHERE key = 'schema_version';
