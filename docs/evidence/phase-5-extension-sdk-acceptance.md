# Phase 5 candidate Extension SDK acceptance

Date: 2026-07-23

Decision: **PASS**

Exit gate: **The shipped reference extension passes the reusable conformance suite
independently of Marketing.**

Phase 4 prerequisite: **PASS**, recorded in
[`phase-4-extension-outcome-acceptance.md`](phase-4-extension-outcome-acceptance.md).

This decision accepts only Phase 5 capability negotiation, the candidate Python SDK,
provider-free conformance, and the tested current-version integration matrix. Task actions,
their manifests, and the HTTP runtime remain **experimental**. This does not accept Phases 6
or 7, promote E1, add a CLI authority, add an MCP tool, publish a package, or make a
cross-release compatibility promise.

## Candidate SDK surface

The task-action candidate is exported from `core.engine.extensions`:

- `Registry` and the additive `RegisteredTaskAction` registration handle;
- `ExtensionCapabilityManifest`, `ExtensionInvocationEnvelope`,
  `ExtensionActorContext`, and `ExtensionInvocationReceipt`;
- `ExtensionReference`, `ContextResolution`, `ResolvedContextRecord`, and
  `ExtensionTaskPlan`;
- `ExtensionOutcome` and `ExtensionArtifactProvenance`; and
- `run_task_action_conformance`.

`Registry.register_task_action(...)` remains experimental and returns the exact action handle
accepted by the provider-free helper. Existing callers may ignore the return. The pre-existing
extension entry point, `Extension` protocol, kill switch, and stable registry methods retain
their documented classifications; this phase does not relabel the task-action surface stable.

## Responsibility boundary

Core owns generic protocol types and validation, scoped registration, deterministic discovery,
version negotiation, actor/product/user/workspace enforcement, reference-accounting invariants,
ordinary durable task execution, idempotency, attempt lineage, cancellation state, bounded
receipt normalization, credential redaction, raw-output preservation, generic outcome/artifact
validation, schemas, and runtime conformance fixtures.

An extension owns domain references and repositories, extra domain authorization, preparation,
private resolved content, deterministic output projection and optional domain validation,
artifact creation and domain provenance, feature meaning, and product UX. Core contains no
Marketing import, field, parser, repository, or action.

## Manifest and registration rules

Every public manifest exposes extension ID and version, action name and bounded description,
accepted input versions, one output version, lifecycle operations, cancellation support,
resolver and artifact capabilities, required authorities and feature flags, and the literal
`experimental` stability label.

Registration requires an extension-scoped registry. Exact duplicate pairs are rejected. The
internal identity is the tuple `(extension_id, action_name)`, so delimiter characters cannot
collapse distinct pairs. Identifier grammar and bounds are validated. Empty required lists,
duplicate list values including lifecycle operations, and cancellation support without `cancel`
are rejected.

The registry accepts at most 200 task actions and discovery defensively enforces the same limit.
Discovery sorts by the identity tuple, so registration order does not affect output. Public
manifests are revalidated and omit preparation, resolver, projector, and validator callables.
With `ACE_DISABLE_EXTENSIONS=1`, discovery and the task-action registry remain empty.

## Provider-free versus runtime conformance

`run_task_action_conformance` makes no provider or database call. Its 15 checks cover:

1. manifest validity;
2. deterministic manifest output;
3. callable-free public manifest output;
4. input-version negotiation;
5. task preparation and exact reference accounting;
6. output projection plus optional validation;
7. deterministic outcome projection;
8. public receipt-schema validity;
9. public receipt bounds;
10. private plan exclusion;
11. private resolver-content exclusion;
12. recommendation/decision/adoption separation;
13. projection-failure degradation with raw Core output preserved;
14. credential redaction; and
15. immutable artifact and exact provenance rejection rules.

The helper cannot establish durable runtime behavior. Core runtime tests own idempotency,
duplicate-key conflict, product/user/workspace isolation, restart reconstruction, concurrent
resume, attempt N+1, cancellation, unavailable extensions, malicious stored payloads, and
bounded public reconstruction.

## Scenario-to-test evidence

| Required scenario | Primary evidence | Result |
|---|---|---|
| Registry scope, duplicate registration, invalid values, identity ambiguity, and 200-action bound | `tests/extensions/test_task_actions.py` | Pass |
| Deterministic bounded callable-free capability discovery and schema catalog | `tests/test_extension_invocations_api.py` | Pass |
| Provider-free reusable conformance | `test_provider_free_conformance_covers_manifest_plan_outcome_and_receipt` | Pass, 15 checks |
| Shipped reference extension independent conformance | `test_reference_action_passes_provider_free_conformance_without_marketing` | Pass |
| Clean scaffold conformance | `test_scaffolded_action_passes_provider_free_conformance`; tutorial flow tests | Pass |
| Valid submission and completed receipt | extension API and task public-contract tests | Pass |
| Idempotent replay and duplicate-key conflict | `tests/test_task_public_contract.py` | Pass |
| Projection and validator failure; raw output preservation | task-action and public-contract tests | Pass |
| Missing/rejected references | task-action and Marketing resolver tests | Pass |
| Extension unavailable after restart | `test_resume_fails_closed_when_extension_is_unavailable_after_restart` | Pass |
| Product, user, and workspace isolation | extension API access tests | Pass |
| Runtime restart | real SurrealKV/two-process restart test | Pass |
| Concurrent resume and attempt N+1 | extension API concurrency and retry-lineage tests | Pass |
| Cancellation | extension API and public task cancellation tests | Pass |
| Unknown versions and malicious payloads | compatibility fixtures and lookup tests | Pass |
| Bounded and redacted public output | task-action, fixture, and public-contract tests | Pass |
| Immutable artifact provenance | outcome validation, reconstruction, and conformance helper | Pass |
| Exact eleven-tool thin MCP boundary | MCP spec/tool and kernel-boundary tests | Pass |

## Compatibility matrix

| Combination | Result |
|---|---|
| Current Core + current shipped reference extension | Pass: independent 15-check helper, reference tests, runtime suite |
| Current Core + current B2B Marketing extension | Pass: 15-check helper, 355 Python tests, focused resolver tests, 3 adapter Vitest tests |
| Current Core + no extensions | Pass: loader/registry assertions, full naked suite, naked Canvas build |
| Extension version omitted | Pass: resolves the currently registered action |
| Exact registered extension version | Pass |
| Mismatched extension version | Pass: generic 409 without reflecting untrusted input |
| Accepted `extension-invocation-v1` input | Pass |
| Unsupported input version | Pass: schema rejection and fail-closed lookup fixture |
| Correct registered output version | Pass |
| Incorrect projected or stored output version | Pass: projection rejection or empty degraded reconstruction |
| Extension unavailable during resume | Pass: no successor submission |

No N-1, future-Core/current-extension, current-Core/future-extension, mixed wheel, or general
cross-release matrix was executed. Those combinations are explicitly untested and unsupported
by this acceptance. An omitted extension version selects the currently loaded implementation; it
is not a compatibility guarantee across releases.

## Independent reference and builder evidence

The shipped `extensions/reference` package registers one bounded
`product:product-check` task action. Its preparation accounts for every reference as
`declared`, because it has no repository adapter; it never fabricates retrieval. Its projector
uses only generic task-action and outcome types, is deterministic, creates no artifact claim, and
contains no Marketing import or semantics.

The scaffold still copies that exact reference package, now renames the preparation/projector
functions as well as action and contract identities, and passes the reusable helper from a clean
temporary package. The builder guide contains the executable registration-handle-to-conformance
journey. No Marketing code is copied or required.

## Marketing second-consumer evidence

B2B Marketing remains a separate extension. Its action uses the same generic Core types,
declares unsupported reference kinds honestly, resolves the supported prior-decision kind with
product scope plus immutable version/hash evidence, and projects its own domain outcome. The
provider-free helper passes all 15 checks. Its full non-E2E Python suite, focused Ruff checks,
repository-wide Ruff check, and current extension-invocation adapter tests pass. No Marketing
source file was changed for Phase 5.

## Defects corrected during acceptance

1. Colon-delimited string registry keys could collapse two distinct valid identity pairs. The
   internal registry now keys directly by `(extension_id, action_name)` without narrowing the
   frozen v1 identifier grammar.
2. The 200-action maximum was enforced only during discovery. Registration now fails before a
   201st action can enter the store; discovery retains a defensive check.
3. Duplicate lifecycle operations were not rejected, and explicit empty input/lifecycle lists
   were silently replaced by defaults. Required lists now preserve explicit emptiness for
   validation, and every manifest list rejects duplicates.
4. `ExtensionCapabilityManifest` checked shape but did not independently re-enforce identifier,
   list, lifecycle, cancellation, and bound invariants. It now validates the public record
   directly.
5. The reusable helper did not explicitly prove callable exclusion or immutable/exact artifact
   provenance rejection. Both are now named checks.
6. Registration discarded the action handle required by the public helper. It now returns that
   handle additively, and the relevant types are exported from the candidate SDK.
7. The scaffold retained reference-specific preparation/projector function names and lacked an
   executed clean-package conformance journey. Function names are now renamed, the scaffold test
   runs the helper, and the builder guide shows the same path.
8. Independent reference conformance and registration-order determinism were previously inferred
   from generic tests. Dedicated tests now prove both directly.

These changes do not alter the frozen v1 envelope or receipt wire shapes. They tighten invalid
experimental registrations and public manifest validation, replace only an internal ambiguous
key, and add an ignored-compatible return value.

## Exact verification record

Commands were run from `/Users/eamirian/Projects/ace-core` unless noted.

| Command | Result |
|---|---|
| `uv run pytest tests/extensions/test_task_actions.py tests/extensions/test_product_extension.py tests/extensions/test_scaffold_extension.py tests/extensions/test_build_your_first_tutorial.py tests/extensions/test_naked_kernel.py tests/extensions/test_invocation_fixtures.py tests/test_extension_invocations_api.py tests/test_task_public_contract.py tests/test_kernel_boundary.py tests/test_mcp_specs.py tests/test_mcp_tools.py tests/voice/test_proactive_line_extension.py -q --tb=short` | **128 passed** |
| `uv run pytest -m 'not e2e' -q --tb=short` | **6,660 passed, 46 skipped, 235 deselected** |
| `ACE_DISABLE_EXTENSIONS=1 uv run pytest -m 'not e2e and not requires_extensions' -q --tb=short` | **6,650 passed, 47 skipped, 244 deselected** |
| `uv run pytest tests/test_i1_restart_persistence.py -q --tb=short` | **1 passed in 24.27s** |
| From Marketing: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/eamirian/Projects/ace-ext-b2b-marketing /Users/eamirian/Projects/ace-core/.venv/bin/pytest ace_ext_b2b_marketing/tests -m 'not e2e' -q --tb=short -p no:cacheprovider` | **355 passed, 4 skipped, 4 deselected** |
| From Marketing: the same Python environment with `ace_ext_b2b_marketing/tests/test_reasoning_invocation.py -q --tb=short -p no:cacheprovider` | **5 passed** |
| From Marketing: the provider-free Python probe reproduced below | **15 checks passed** |
| Core Vitest binary with Marketing `ui/canvas/app/data` as root, an isolated temporary config/cache, and `extension-invocation.test.ts` as the only include | **3 passed** |
| From `core/ui/canvas`: `npm test` | **290 passed** |
| From `core/ui/canvas`: `npm run build:naked` | **9 boundary tests; typecheck and production build passed** |
| From `core/ui/canvas`: `npm run build` | **typecheck and production build passed** |
| `uv run ruff check .` | **passed** |
| `uv run ruff format --check .` | **passed; 1,819 files already formatted** |
| From Marketing: Core's Ruff binary over `reasoning_invocation.py`, `marketing_extension.py`, and `test_reasoning_invocation.py`, then `ruff check --no-cache .` | **both passed** |
| In each repository: `uv build --out-dir <fresh temporary directory>`; Core wheel/sdist inspected with `unzip -l` and `tar -tzf` | **both produced source and wheel artifacts; Core artifacts contain the SDK, reference, scaffold, and builder files** |
| `git diff --check` in both repositories | **passed** |

The exact provider-free Marketing probe constructed a `RegisteredTaskAction` from
`prepare_deep_thinking` and `project_deep_thinking_outcome`, declared the extension's current
lifecycle/resolver/artifact manifest, supplied one immutable declared evidence reference, and ran:

```python
result = asyncio.run(
    run_task_action_conformance(
        action,
        ExtensionInvocationEnvelope(
            extension_id="b2b_marketing",
            extension_version="0.1.0",
            action="deep-thinking",
            workspace_id="workspace:test",
            question="Which reversible messaging test should run first?",
            references=[
                {
                    "namespace": "b2b_marketing",
                    "kind": "evidence",
                    "id": "evidence:one",
                    "digest": "sha256:abc",
                }
            ],
        ),
        ExtensionActorContext(
            product_id="product:test",
            workspace_id="workspace:test",
            user_id="user:test",
        ),
    )
)
assert result["passed"], result
assert len(result["checks"]) == 15
```

## Remaining limitations

- Every task-action and capability-manifest surface remains experimental.
- Extension code is trusted in-process code. Generic validation cannot repair unsafe repository
  authorization, side effects, artifact contents, or domain semantics.
- Provider-free conformance proves callback contracts, not runtime durability, isolation,
  concurrency, cancellation of external work, or exactly-once effects.
- Process-local cancellation cannot undo completed provider calls or extension-owned side effects.
- Artifact validation proves immutable identity and exact declared producer accounting, not
  artifact availability, safety, authorship, or correctness.
- An outcome proves structural conformance, not decision quality, benefit, correctness, approval,
  adoption, or material retained-memory use.
- No live provider, metered call, package publication, commit, push, or release was performed.
- The tested matrix is current-version only. Phases 6 and 7 remain unaccepted.
