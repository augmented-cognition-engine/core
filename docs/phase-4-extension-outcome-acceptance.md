# Phase 4 structured extension-outcomes acceptance

Date: 2026-07-23

Decision: **pass**

Exit gate: **Projection failure degrades honestly.**

The durable extension-invocation runtime remains **experimental**. This acceptance closes only
Phase 4 structured-outcome behavior. It does not accept Phases 5–7, make the HTTP surface a
supported 0.1.x contract, or change the eleven-tool MCP boundary.

## Accepted responsibility boundary

Core owns:

- bounded public normalization and credential redaction;
- preservation and retrieval of usable raw Core output;
- projection invocation only after ordinary task completion;
- projection-failure recording, degraded coverage, and durable receipt retrieval;
- validation of the negotiated outcome contract;
- immutable artifact-reference and exact artifact-provenance validation;
- separation of projected recommendations, governed human decisions, adoption, and memory use;
- task, provider, model, lifecycle, and attempt provenance; and
- fail-closed normalization of malformed or unsupported stored outcomes.

An extension owns:

- its output-contract version and domain meaning;
- deterministic outcome projection and optional domain-specific validation;
- artifact creation, meaning, and domain provenance; and
- any human approval, adoption, or retained-memory workflow.

Core contains no Marketing type, field, parser, or action. The reference extension exercises the
generic contract independently; B2B Marketing supplies its own domain projector and validator.

## Accepted outcome flow

```text
completed ordinary Core task
  → preserve raw Core output and ordinary task/attempt provenance
  → invoke the registered extension projector
  → validate the projected ExtensionOutcome against the negotiated contract
  → validate bounds, immutable artifacts, and exact provenance accounting
  → persist the validated outcome or a bounded projection failure
  → normalize the public extension-invocation-receipt-v1

projector or validator failure
  → ordinary task remains completed
  → raw Core output remains available
  → public outcome is an empty bounded container
  → coverage.state = degraded
  → coverage names extension_outcome_projection
  → failures contains a bounded, credential-redacted outcome_projection_failed record
```

Receipt reconstruction repeats outcome validation. A current receipt containing a malformed
outcome is not trusted merely because it was previously persisted. A stored outcome with a future
contract version projects to an empty current-contract container and explicit degraded coverage;
its artifacts are not reinterpreted.

## Outcome fields

The extension-owned `ExtensionOutcome` has one required field:

- `contract_version`: a non-empty bounded string that must exactly match the registered action's
  negotiated output contract.

The remaining fields are optional with bounded empty defaults:

- `data`: extension-defined public JSON data;
- `artifact_refs`: immutable typed artifact references;
- `artifact_provenance`: one producer-provenance record for each artifact reference; and
- `warnings`: bounded structured warnings.

The Core-owned public receipt keeps these states distinct:

- `raw_core_output`: the usable ordinary Core output, independently available;
- `outcome`: the validated extension projection;
- `artifacts`: the validated created-artifact provenance projection;
- `human_decision`: null unless a separate governed decision receipt exists;
- `adoption`: null until a distinct later adoption workflow exists;
- `provenance`: task/provider/model and linked receipt identities; and
- `coverage` plus `failures`: explicit completeness and degraded-state evidence.

## Artifact and provenance rules

Every `artifact_ref` must include an immutable `version` or `digest`. Artifact references cannot
repeat. Every reference must have exactly one matching `artifact_provenance` entry, and each
provenance entry must name its producer. Provenance cannot omit a declared artifact, introduce an
undeclared artifact, or repeat an artifact identity.

Invalid artifact accounting rejects the projected outcome. The ordinary task and raw output remain
available, while the extension receipt degrades through the same projection-failure path. When a
malformed outcome is encountered during stored-receipt reconstruction, Core emits no artifacts.

## Recommendation, decision, adoption, and memory

Projected recommendations are extension data only. They do not create a decision receipt, approve
the recommendation, record adoption, or retain the recommendation as memory.

`human_decision` remains null until the ordinary governed decision workflow records a distinct
decision. Even then, `adoption` remains null. Adoption or retained-memory use requires a later,
separately attributable workflow. Contract validity therefore does not imply correctness, benefit,
safety, approval, adoption, or material later use.

## Scenario-to-test evidence matrix

| # | Required scenario | Evidence | Result |
|---|---|---|---|
| 1 | Default bounded-content projection succeeds | `test_default_projection_and_registered_validator_succeed` | Pass. The default projector returns the negotiated contract and bounded `data.content`. |
| 2 | Registered output-contract validation succeeds | Same test; `run_task_action_conformance` | Pass. The registered validator is invoked and the validated outcome reaches the receipt. |
| 3 | Wrong output-contract version is rejected | `test_wrong_contract_and_validator_rejection_fail_projection` | Pass before and after the optional validator. |
| 4 | Extension validator rejection degrades honestly | `test_projection_failure_preserves_completed_task_and_raw_output[validator_rejection]` | Pass. Completed status, raw output, and attempt metadata survive; coverage and failure are explicit. |
| 5 | Projector exception degrades honestly | `test_projection_failure_preserves_completed_task_and_raw_output[projector_exception]`; conformance helper | Pass with the same bounded failure path. |
| 6 | Raw Core output survives projection failure | Both public-contract projection-failure cases | Pass. `raw_core_output.available` remains true and content remains retrievable. |
| 7 | Projection failure is credential-redacted | Both public-contract projection-failure cases | Pass. Tokens in exception text and raw output are redacted. |
| 8 | Valid immutable artifact plus matching provenance succeeds | `test_outcome_artifacts_require_immutable_matching_provenance` | Pass. Versioned reference and its sole matching producer record are returned. |
| 9 | Mutable artifact reference is rejected | Same artifact test | Pass. A reference lacking both version and digest fails validation. |
| 10 | Missing artifact provenance is rejected | Same artifact test | Pass. Exact accounting is required. |
| 11 | Extra or duplicate artifact provenance is rejected | Same artifact test | Pass. Extra, duplicate-provenance, and duplicate-reference cases all fail. |
| 12 | Outcome-size limits are enforced | `test_outcome_size_limit_is_enforced`; `test_outcome_bounds_nested_redaction_artifacts_and_decision_separation` | Pass. Oversized serialized outcomes fail validation; collections and public projections are bounded. |
| 13 | Nested malicious output is bounded and redacted | Same bounds/redaction test; `malformed-outcome-receipt-v1.json` | Pass. Sensitive keys including private prompts, tokens, and resolver state are redacted; nesting and item counts are bounded. |
| 14 | Recommendation, human decision, and adoption remain separate | Same bounds/separation test; conformance helper | Pass. Projection alone leaves both governed states null; a later decision populates only `human_decision`. |
| 15 | Future receipt/outcome versions fail closed | Existing future receipt fixture; `future-outcome-receipt-v1.json`; `malformed-outcome-receipt-v1.json` | Pass. Unsupported/malformed stored outcomes produce empty degraded projections with no artifacts. |
| 16 | Marketing projector emits only deterministically validated fields | `test_outcome_projection_is_structured_and_honest_about_partial_execution`; deterministic projector replay assertion | Pass. Equal input produces equal output with the declared Marketing field set. |
| 17 | Ambiguous Marketing output remains an honest bounded-content container | Deterministic projector assertion using ambiguous prose | Pass. The prose remains recommendation content; alternatives, assumptions, evidence, and reconsideration arrays remain empty rather than fabricated. |
| 18 | Reference extension demonstrates the generic contract independently of Marketing | `test_reference_projector_is_generic_deterministic_bounded_content`; reference action/conformance tests | Pass. The generic reference projector is deterministic and contains no Marketing semantics. |
| 19 | Naked kernel stays domain-neutral and passes its boundaries | `tests/test_kernel_boundary.py`; full extensions-disabled suite; Canvas naked build | Pass. No Marketing concept was added to Core and all naked gates are green. |

## Defects corrected during acceptance

1. Public receipt reconstruction accepted a persisted outcome dictionary without repeating
   `ExtensionOutcome` validation or checking it against the persisted negotiated output contract.
   A malformed current outcome or future outcome contract could therefore be reinterpreted,
   including artifact data. Reconstruction now validates again and degrades to an empty outcome
   with an explicit bounded failure.
2. Duplicate artifact references were collapsed by set comparison and could pass exact provenance
   accounting. Duplicate artifact references now fail validation directly.
3. Arbitrary `resolver_state` and `private_resolver` keys were not part of sensitive-key
   normalization. They are now redacted recursively along with credentials and private prompts.
4. The provider-free conformance helper did not explicitly demonstrate deterministic projection or
   recommendation/decision/adoption separation. It now repeats projection and records both checks.
5. Focused evidence did not directly cover registered-validator rejection, projector exceptions,
   malformed stored outcomes, nested bounds/redaction, exact artifact accounting, or the generic
   reference projector. Provider-free tests and compatibility fixtures now cover those paths.

These are additive validation, redaction, conformance, fixture, and documentation changes. The
frozen v1 envelope and receipt shapes are unchanged. Invalid outcomes that contradicted the
documented v1 invariants now fail closed; no valid v1 producer needs a wire-format change. No B2B
Marketing product code change was required.

## Exact verification record

Commands were run from `/Users/eamirian/Projects/ace-core` unless noted.

| Command | Result |
|---|---|
| `uv run pytest tests/extensions/test_task_actions.py tests/extensions/test_invocation_fixtures.py tests/extensions/test_product_extension.py tests/test_task_public_contract.py -q --tb=short` | **49 passed** |
| `uv run pytest tests/extensions/test_task_actions.py tests/extensions/test_invocation_fixtures.py tests/extensions/test_product_extension.py tests/test_extension_invocations_api.py tests/test_task_public_contract.py tests/test_kernel_boundary.py -q --tb=short` | **78 passed** |
| `uv run pytest tests/extensions tests/test_extension_invocations_api.py tests/test_extension_registry.py tests/test_kernel_boundary.py tests/test_mcp_specs.py tests/test_mcp_tools.py tests/voice/test_proactive_line_extension.py -q --tb=short` | **112 passed** |
| `uv run pytest -m 'not e2e' -q --tb=short` | **6,653 passed, 46 skipped, 235 deselected in 388.42s** |
| `ACE_DISABLE_EXTENSIONS=1 uv run pytest -m 'not e2e and not requires_extensions' -q --tb=short` | **6,644 passed, 47 skipped, 243 deselected in 380.49s** |
| `PYTHONPATH=/Users/eamirian/Projects/ace-ext-b2b-marketing /Users/eamirian/Projects/ace-core/.venv/bin/pytest /Users/eamirian/Projects/ace-ext-b2b-marketing/ace_ext_b2b_marketing/tests -m 'not e2e' -q --tb=short -p no:cacheprovider` | **355 passed, 4 skipped, 4 deselected** |
| `PYTHONPATH=/Users/eamirian/Projects/ace-ext-b2b-marketing /Users/eamirian/Projects/ace-core/.venv/bin/pytest /Users/eamirian/Projects/ace-ext-b2b-marketing/ace_ext_b2b_marketing/tests/test_reasoning_invocation.py -q --tb=short -p no:cacheprovider` | **5 passed** |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/eamirian/Projects/ace-ext-b2b-marketing /Users/eamirian/Projects/ace-core/.venv/bin/python -c '<deterministic bounded-content assertions below>'` | **passed: `marketing projector: deterministic bounded-content PASS`** |
| Isolated unchanged Marketing `extension-invocation.test.ts` using Core's Vitest runtime | **3 passed** |
| `(cd core/ui/canvas && npm test)` | **290 passed** |
| `(cd core/ui/canvas && npm run build:naked)` | **9 boundary tests passed; TypeScript and production build passed** |
| `(cd core/ui/canvas && npm run build)` | **TypeScript and production build passed** |
| `uv run ruff check .` | **passed** |
| `uv run ruff format --check .` | **passed; 1,819 files already formatted** |
| `/Users/eamirian/Projects/ace-core/.venv/bin/ruff check --no-cache /Users/eamirian/Projects/ace-ext-b2b-marketing/ace_ext_b2b_marketing/reasoning_invocation.py /Users/eamirian/Projects/ace-ext-b2b-marketing/ace_ext_b2b_marketing/marketing_extension.py /Users/eamirian/Projects/ace-ext-b2b-marketing/ace_ext_b2b_marketing/tests/test_reasoning_invocation.py` | **passed** |
| Marketing-wide Ruff check | **29 pre-existing `I001` import-order findings in unrelated files; no Phase 4 finding and no bulk rewrite applied** |
| `git diff --check` in each repository | **passed after final reconciliation** |

The exact deterministic Marketing assertion body was:

```python
from ace_ext_b2b_marketing.reasoning_invocation import project_deep_thinking_outcome

output = "Lead with governance, but the evidence is ambiguous."
execution = {"state": "partial"}
first = project_deep_thinking_outcome(output, execution)
second = project_deep_thinking_outcome(output, execution)
expected = {
    "recommendation_content",
    "alternatives",
    "assumptions",
    "evidence_refs",
    "reconsideration_conditions",
    "execution_state",
    "projection",
}
assert first == second
assert set(first.data) == expected
assert first.data["recommendation_content"] == output
assert (
    first.data["alternatives"]
    == first.data["assumptions"]
    == first.data["evidence_refs"]
    == first.data["reconsideration_conditions"]
    == []
)
assert first.data["projection"] == "bounded_content_container"
print("marketing projector: deterministic bounded-content PASS")
```

The Marketing Canvas is not currently wired into the Core Vitest include roots, and no
artifact-specific Marketing receipt UI test exists in the current worktrees. The three relevant
receipt-adapter tests were copied unchanged to a temporary fixture, run against Core's installed
Vitest runtime, and removed. No repository file was created or modified for that run.

The Marketing-wide Python result and focused projector/resolver results include the current
reference implementation without making a live provider or metered call.

Marketing-wide Ruff is not currently clean: a no-cache scan reports 29 import-order findings in
pre-existing, unrelated source and test files. The Phase 4 projector, extension registration, and
reasoning test files are clean. Because the Marketing worktree contains concurrent user changes
and Phase 4 did not modify it, this acceptance does not apply a repository-wide import rewrite.

## Verified limitations and risks

- A valid structured outcome proves bounded contract conformance, not semantic correctness,
  benefit, safety, or faithful domain interpretation.
- Extension code remains trusted in-process code. Core public normalization cannot make an unsafe
  extension repository adapter or artifact producer safe.
- Raw output and outcome data are bounded and redacted public projections, not private execution
  transcripts.
- Artifact validation proves immutable identity and exact declared producer accounting. It does
  not prove artifact contents, authorship, safety, or availability.
- A governed decision is separate from a recommendation, and adoption remains unimplemented on
  this surface. No retained-memory use is inferred.
- Future or malformed outcomes fail closed and cannot expose artifacts, but this in-tree evidence
  is not a multi-package version-skew matrix.
- The Marketing ambiguous-output case preserves a bounded honest container; it does not claim that
  the projector understands arbitrary prose.
- No live-provider, metered, publication, or release action was performed.
- The runtime and HTTP surface remain experimental. Phases 5–7 remain unaccepted.
