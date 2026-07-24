# Phase 7 — Extension-invocation stabilization review

Date: 2026-07-23
Decision: **CONDITIONAL PASS**
Stable promotion authorized: **none**

## Exit gate

> Review extension invocation as a stability candidate across Core and the
> B2B Marketing consumer. Re-run conformance, compatibility, recovery,
> security, packaging, naked-kernel, and product-experience acceptance; fix
> required defects; then record PASS, CONDITIONAL PASS, or FAIL without
> promoting an API beyond the available evidence.

The current Core and Marketing implementations are internally consistent,
provider-free conformance passes, both full Python suites pass, real
restart persistence passes, naked Core passes, both clean distributions are
discoverable, and the wired browser journey remains usable and accessible.
One packaging-hygiene defect was found and fixed in Marketing.

The decision is conditional because the review does not establish an N-1
multi-package compatibility promise, process isolation, distributed
claim/recovery guarantees, exactly-once external effects, independent security
review, or complete extension-specific operational/resource telemetry. Those
are promotion blockers, not hidden follow-up. The existing v1 contracts remain
experimental and supported in their documented current-version scope.

Phase 6 is the product-experience prerequisite:
[`phase-6-extension-product-experience-acceptance.md`](phase-6-extension-product-experience-acceptance.md).

## Reviewed surface classification

| Surface | Phase 7 classification | Rationale |
| --- | --- | --- |
| Existing `Extension` protocol, registry lookup, entry-point loading, and `ACE_DISABLE_EXTENSIONS` | Existing supported extension API | Already documented in the Extension API; this review found no regression |
| `extension-invocation-v1`, receipt/history/list v1 DTOs, bounded error/degraded taxonomy | Stability candidates only | Frozen, deterministic, provider-free conformance and current-version consumer checks pass; no cross-release promotion evidence |
| Task-action registration, capability manifest, and `RegisteredTaskAction` | Experimental, supported | Useful SDK/runtime seam, but trusted in-process execution and compatibility policy remain incomplete |
| Submit, task read, history, resume, cancel, and list HTTP routes | Experimental, supported | Authenticated and tested, but lifecycle authority and distributed recovery are not stable promises |
| Linked retry, cancellation, structured outcomes/artifacts, and Canvas wiring | Experimental, supported | Accepted behavior in current Core/Marketing; process-local and consumer-specific limits remain |
| Persistence metadata, locks, reconstruction, normalization, and store internals | Internal | Implementation detail, not an extension-author compatibility contract |
| Cross-release SDK promise, isolated execution, distributed claiming, exactly-once effects, resource guarantees | Deferred | Evidence or implementation required before promotion |

No public surface changed classification to stable in this review.

## Compatibility and conformance

| Pair or posture | Evidence | Result |
| --- | --- | --- |
| Current Core + reference extension | Frozen fixtures, reference registration/action, scaffold, tutorial, and clean-wheel entry point | PASS |
| Current Core + current Marketing | Provider-free 15-check action probe, full Marketing tests, combined clean-wheel discovery, wired Canvas | PASS |
| Zero extensions | `ACE_DISABLE_EXTENSIONS=1` full suite plus naked Canvas production build/leakage test | PASS |
| Omitted/exact/mismatched extension version | Phase 5 matrix rerun through the focused invocation fixtures | PASS |
| Accepted/unsupported input and correct/incorrect output | Provider-free conformance and malicious/invalid fixtures | PASS |
| Extension unavailable during resume | Focused lifecycle/API fixtures | PASS |
| Core/consumer N-1 and multi-release skew | No independently packaged N-1 matrix exists | **NOT VERIFIED — promotion blocker** |

The frozen v1 wire shapes were not changed. The review did not reinterpret
unknown or mismatched versions as v1.

## Security, privacy, and authority review

| Area | Finding | Disposition |
| --- | --- | --- |
| Authentication and product/workspace isolation | API and public-contract suites cover unauthorized, foreign-scope, missing, invalid, and bounded list/read behavior | PASS for current runtime |
| Redaction and bounded output | Recursive secret-like fields, provider errors, invalid outcomes, artifacts, and arbitrary detail remain fail-closed or redacted | PASS |
| Invocation authority | Extensions receive registered action authority only; no new CLI or MCP authority was added and the eleven-tool MCP boundary passed | PASS |
| UI rendering | Public receipt fields render as React text/`pre`; recovery copy discards arbitrary server detail; no unsafe HTML sink was introduced | PASS |
| Package contents | Core and Marketing wheels contain declared entry points and omit credentials; Marketing tests are now excluded from wheel and sdist | PASS after fix |
| Execution containment | Extension code executes in the trusted Core process | **Promotion blocker** |
| Independent security assessment | No independent review or adversarial process-isolation assessment was performed | **Promotion blocker** |

The current threat boundary is therefore suitable for explicitly trusted,
installed extensions, not untrusted third-party code.

## Recovery and operability

Durable receipts expose task/receipt/invocation identity, correlation ID,
attempt number, root and predecessor/successor lineage, retry reason/actor/time/
policy, status, terminal/resumable state, provider/model provenance, coverage,
reference resolution, artifacts, cancellation state, and bounded public error
information. Real restart persistence and fresh-process reconstruction pass.

The following remain outside the accepted guarantee:

- cancellation coordination is process-local and cannot reverse a completed
  provider or other external side effect;
- retry coordination uses a single-runtime lock and is not a distributed task
  claim/lease protocol;
- no exactly-once guarantee exists for external effects;
- extension-specific queue depth, lease age, cancellation progress, resource
  ceilings, provider cost, and saturation metrics are incomplete;
- recovery under multi-worker crash/partition conditions was not established.

These limitations keep the invocation runtime experimental even though its
current single-runtime behavior is reproducible.

## Product-experience regression

The current Core+Marketing source was assembled through the supported one-line
Canvas extension-registration shim and exercised against a deterministic local
receipt server. No provider, model, credential, external connection, or metered
call was used.

- A completed durable receipt rendered its public input, exact resolution
  posture, provenance, outcome, raw output, decision/adoption empty states, and
  two-attempt history.
- The linked successor opened as attempt 2 with the correct predecessor and
  retry metadata.
- An active attempt exposed negotiated cancellation and returned a distinct
  cancelled/acknowledged receipt.
- Prepared Atrium remained a separately named demonstration, never a fallback.
- One `main` and one `h1` rendered at every tested viewport.
- 320×568, 375×667, 390×844, 768×1024, and 1440×900 each matched document
  width, had no horizontal overflow, and had zero visible button/input/textarea
  controls below 44px.
- Mobile navigation opened with Enter, focused its first item, closed with
  Escape, and restored focus to the trigger.
- The browser console contained zero warnings and zero errors.

The scratch harness used symlinked Core dependencies. Vite logged two
harness-only filesystem allow-list messages for font files; these were not
browser console errors, did not affect control geometry, and are absent from
the real Core production build.

Late-arriving user-owned Market Intelligence and Memory operating-canvas
refactors were copied into the harness before final acceptance. They initially
exposed three consumer regressions: a nested second `main`, a shortened button
label that broke the established accessible name, and newly repeated receipt
identities that made uniqueness-based tests invalid. The narrow fixes preserve
the refactor while restoring one-main semantics, the stable accessible name,
design-token enforcement, and multiplicity-aware assertions. The final
479-test/typecheck/build results below include those changes.

## Packaging review and defect fixed

The committed Core source was built from a clean `git archive` into an sdist
and wheel. The wheel imported as `ace-core` 0.1.2, exposed exactly the
`product` extension entry point, loaded `ProductExtension`, included schema
v157, excluded Marketing, and omitted Core tests.

The first Marketing package inventory exposed a real defect: its wheel and
sdist shipped `ace_ext_b2b_marketing/tests`. The fix:

1. excludes `ace_ext_b2b_marketing.tests*` from setuptools package discovery;
2. prunes `ace_ext_b2b_marketing/tests` from the sdist via `MANIFEST.in`;
3. adds a regression test for both declarations.

Rebuilt Marketing wheel and sdist inventories contain no tests. Installing the
fixed Marketing wheel alongside the clean Core wheel exposed exactly
`b2b_marketing` and `product`; both entry points loaded, and
`ace_ext_b2b_marketing.tests` was absent.

## Verification commands and exact results

```bash
# Focused stabilization/conformance/security/schema/MCP matrix
uv run pytest \
  tests/extensions/test_task_actions.py \
  tests/extensions/test_product_extension.py \
  tests/extensions/test_scaffold_extension.py \
  tests/extensions/test_build_your_first_tutorial.py \
  tests/extensions/test_naked_kernel.py \
  tests/extensions/test_invocation_fixtures.py \
  tests/test_extension_invocations_api.py \
  tests/test_task_public_contract.py \
  tests/test_extension_registry.py \
  tests/test_kernel_boundary.py \
  tests/test_mcp_specs.py \
  tests/test_mcp_tools.py \
  tests/voice/test_proactive_line_extension.py \
  tests/test_schema_migration_lint.py \
  tests/test_schema_migration_errors.py \
  tests/test_migration_safety.py \
  -q --tb=short
# 154 passed

uv run pytest -m 'not e2e' -q --tb=short
# 6,660 passed, 46 skipped, 235 deselected, 28 warnings

ACE_DISABLE_EXTENSIONS=1 \
  uv run pytest -m 'not e2e and not requires_extensions' -q --tb=short
# 6,650 passed, 47 skipped, 244 deselected, 28 warnings

uv run pytest tests/test_i1_restart_persistence.py -q --tb=short
# 1 passed in 30.04s

uv run ruff check .
# All checks passed

uv run ruff format --check .
# 1,819 files already formatted

actionlint
# passed

# Marketing, using Core's environment and no provider
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/eamirian/Projects/ace-ext-b2b-marketing \
  /Users/eamirian/Projects/ace-core/.venv/bin/pytest \
  ace_ext_b2b_marketing/tests -m 'not e2e' \
  -q --tb=short -p no:cacheprovider
# 356 passed, 4 skipped, 4 deselected

/Users/eamirian/Projects/ace-core/.venv/bin/ruff check --no-cache .
# All checks passed

/Users/eamirian/Projects/ace-core/.venv/bin/ruff format --no-cache --check \
  ace_ext_b2b_marketing/tests/test_packaging_hygiene.py
# 1 file already formatted

# Direct Marketing RegisteredTaskAction provider-free conformance
# 15 checks passed

# Core Canvas
npm test -- --run --reporter=basic
# 32 files, 291 tests passed

npm run build
# TypeScript + production Vite build passed; 7,382 modules transformed

npm run build:naked
# naked TypeScript + Vite build passed; 7,382 modules transformed
# naked extension-leakage test: 1 file, 9 tests passed

# Wired Core + Marketing Canvas scratch harness
./node_modules/.bin/vitest run --reporter=basic
# 61 files, 479 tests passed

./node_modules/.bin/tsc --noEmit
# passed

npm run build
# TypeScript + production Vite build passed; 7,456 modules transformed
```

Clean Core and Marketing sdist/wheel builds, archive inventories, clean-venv
imports, schema presence, entry-point discovery, combined entry-point loading,
and test-package exclusion also passed. No artifact was published.

The first naked-kernel run was mistakenly overlapped with the enabled suite and
reported five unrelated voice-test database WebSocket timeouts. The exact five
tests immediately passed alone (10 tests), and the required full naked suite
then passed sequentially with the result recorded above. The transient
parallel-contention run is not counted as acceptance evidence.

## Worktree and scope preservation

- No branch was created or switched.
- No file was staged, committed, pushed, published, reset, overwritten, or
  discarded.
- Existing uncommitted Marketing work was preserved and included in the wired
  acceptance runs. Late-arriving operating-canvas changes were not discarded;
  they received only the narrow semantic/accessibility/token/test fixes
  described above.
- No live provider or metered call was made.

## Changed files

Core changes owned by Phase 7:

- `docs/phase-7-extension-invocation-stabilization-review.md` — this decision,
  evidence, limitations, and promotion blockers;
- `docs/README.md` — Phase 6 and Phase 7 evidence links;
- `docs/roadmap-status.md` — reconciled E1 without promoting it.

Marketing changes owned by Phase 7:

- `pyproject.toml` — exclude the internal test package from wheel discovery;
- `MANIFEST.in` — prune internal tests from the sdist;
- `ace_ext_b2b_marketing/tests/test_packaging_hygiene.py` — package-regression
  assertion;
- `ace_ext_b2b_marketing/ui/canvas/app/B2BMarketingMarketIntelligence.tsx` —
  preserve the established prepared-reference accessible name in the
  late-arriving refactor;
- `ace_ext_b2b_marketing/ui/canvas/app/B2BMarketingOperatingCanvas.tsx` — avoid
  a nested `main` and satisfy the shared contrast-token enforcement rule;
- `ace_ext_b2b_marketing/ui/canvas/app/B2BMarketingMemory.test.tsx` — assert
  repeated, truthful receipt identities without assuming global uniqueness.

At closeout, Core remains on
`wip/extension-invocation-lineage` tracking its same-named upstream. Marketing
remains on `codex/px5-market-intelligence`, one commit ahead of its upstream,
with pre-existing and concurrently added user-owned changes still present.

## Promotion blockers and next evidence

Before any invocation SDK/runtime promotion, require:

1. a published-package N-1/current compatibility matrix covering Core,
   reference/scaffold, and at least one independent consumer;
2. an explicit trusted-versus-isolated extension threat model and independent
   security review, with isolation if untrusted code is in scope;
3. distributed task claiming/lease/recovery semantics and an honest external
   side-effect policy;
4. extension-specific operational metrics, resource ceilings, and
   cancellation/recovery observability;
5. a documented compatibility/deprecation window and named authority for the
   promotion decision.

## Final acceptance

**CONDITIONAL PASS.** The current implementation is a credible stability
candidate and all required current-version, naked-kernel, restart, packaging,
security-regression, consumer, build, and browser lanes pass after the
Marketing packaging fix. No surface is promoted to stable. E1 remains not
ready until the stated cross-release, isolation/security, distributed
recovery/effects, and operability blockers are closed.
