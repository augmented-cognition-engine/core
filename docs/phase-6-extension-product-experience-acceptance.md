# Phase 6 — Extension-invocation product-experience acceptance

Date: 2026-07-23
Decision: **PASS**

## Exit gate

> History, receipts, refresh/recovery, mobile usability, and accessibility
> verification pass.

The wired B2B Marketing Deep Thinking journey passes this gate with a
deterministic local Core-receipt fixture. No provider, model, external
connection, credential, or metered call was used. The frozen
`extension-invocation-v1` and `extension-invocation-receipt-v1` wire contracts
were not changed. Core remains domain-neutral, Marketing presentation remains
extension-owned, the Canvas extension seam remains experimental, and this
decision does not accept Phase 7.

Phase 5's recorded PASS is the prerequisite baseline:
[`docs/phase-5-extension-sdk-acceptance.md`](phase-5-extension-sdk-acceptance.md).

## Tested journey and scenario matrix

| Requirement | Deterministic acceptance evidence | Result |
| --- | --- | --- |
| Explicit live launch | Browser filled the named question field and activated `Start durable attempt`; the local fixture accepted exactly one POST | PASS |
| Task identity in URL | Accepted `task:live` became `?task=task%3Alive` | PASS |
| Refresh/direct reopen | Reload retained the exact URL and reopened `receipt:task:live`; direct `task:completed` reopen also passed | PASS |
| Poll without duplicate work | Vitest proves one task identity, one interval lifecycle, no POST during polling, and terminal shutdown | PASS |
| Complete ordered history | Browser and Vitest show root then successor in the Core-validated order | PASS |
| Current/predecessor/successor | Current badge, predecessor/successor IDs, and named open controls render from public receipt fields | PASS |
| Retry detail | Reason, actor, timestamp, policy, provider, model, and coverage are independently labeled | PASS |
| Reference resolution | Every supplied reference is paired with `resolved`, `declared`, `missing`, or `rejected`; the browser fixture showed `evidence:browser` as `declared` | PASS |
| Idempotent eligible retry | Only failed/degraded, resumable attempts expose retry; an immediate double activation produced one resume request in Vitest | PASS |
| Negotiated cancellation | Cancel is absent when unsupported and present only for active attempts whose receipt says `supported: true` | PASS |
| Distinct cancellation states | Browser verified `available` to `acknowledged`, actor, request time, acknowledgement time, and terminal `cancelled` | PASS |
| Separate result concepts | Raw Core output, projected outcome, artifacts, human decision, and adoption have separate named regions and explicit empty states | PASS |
| Privacy | Core's public receipt/redaction tests pass; UI recovery copy never renders server detail; no `dangerouslySetInnerHTML` sink exists in this journey | PASS |
| Prepared/live separation | A live status announcement names the durable task; prepared Atrium has a distinct accessible name and is never a live fallback | PASS |
| Failed live remains failed | Missing, invalid, unauthorized, foreign-scope, transient, failed, and degraded states do not substitute prepared output | PASS |

The retry browser path finished with:

- URL `?task=task%3Aretry`;
- receipt input `task:retry`;
- detail `#2 · completed`;
- ordered history `task:failed` then `task:retry`;
- predecessor `task:failed`;
- reason `user_requested_retry`;
- actor `user:browser`;
- timestamp `2026-07-23T18:00:00Z`;
- policy `linked-attempt-v1`;
- provider/model `fixture` / `fixture:model`.

## Refresh and recovery

| Scenario | Observed behavior | Result |
| --- | --- | --- |
| URL reload | Same URL and exact durable receipt; no relaunch | PASS |
| Direct reopen | Loading announcement precedes the returned live receipt | PASS |
| Back/forward | Navigates among existing receipt URLs; no launch action occurs | PASS |
| Missing ID | `Invocation not found`; zero receipt content; no prepared substitution | PASS |
| Unauthorized/foreign scope | `Invocation unavailable`; contents undisclosed; zero receipt content | PASS |
| Invalid ID/lineage | Explicit invalid-link state; oversized IDs fail before network access | PASS |
| Transient retrieval/polling | Labeled as temporary Core reachability, not durable task failure | PASS |
| Restart-like degradation | A named `Retry receipt retrieval` action reuses the retained task ID | PASS |
| Terminal state | Polling interval is cleared after completed/failed/degraded/cancelled | PASS |
| History convergence | History reloads when task status changes, so detail and chain cannot diverge | PASS |
| Empty/partial/error | Explicit no-receipt, degraded coverage, history error, and request error copy | PASS |

## Mobile and responsive acceptance

The in-app browser exercised the supported one-line extension-registration shim
and same-origin Canvas proxy against a local deterministic receipt server.

| Viewport | Document width | Essential horizontal overflow | Undersized visible control | Fixed/sticky overlay outside viewport |
| --- | ---: | --- | ---: | ---: |
| 320×568 | 320 | none | 0 | 0 |
| 375×667 | 375 | none | 0 | 0 |
| 390×844 | 390 | none | 0 | 0 |
| 768×1024 | 768 | none | 0 | 0 |
| 1440×900 | 1440 | none | 0 | 0 |

Receipt IDs, references, raw output, outcome JSON, and attempt lineage wrap or
use bounded internal scrolling without widening the page. All visible buttons,
links, inputs, textareas, selects, desktop sidebar entries, and mobile menu
items met the 44px touch-target floor after the fixes. The open mobile menu
remained inside the 390×844 viewport and used bounded vertical scrolling.

## Accessibility acceptance

- One `main` and one level-one heading rendered at every tested viewport.
- All visible interactive controls in the measured journey had accessible
  names; the browser found zero unlabeled controls.
- Live invocation state is a polite status announcement. Prepared Atrium is a
  separately named link and never shares the live result region.
- Retry, cancel, refresh history, attempt selection, reopen, predecessor,
  successor, reference resolution, and artifact regions have explicit names.
- The mobile menu opened with Enter, exposed `menu`/`menuitem` semantics, closed
  with Escape, and restored focus to its trigger.
- Focusable journey controls accept programmatic keyboard focus and retain the
  shared focus-ring treatment. Focus targets remain inside the viewport.
- State is always repeated in text (`pending`, `completed`, `failed`,
  `degraded`, `cancelled`, resolution and cancellation labels), not color alone.
- The extension's `prefers-reduced-motion: reduce` rule reduces animation and
  transition duration and disables smooth scrolling.
- No dialog is part of this journey. The active overlay is the Radix mobile
  menu; its focus restoration and Escape behavior were exercised.
- Core's 20-test AA suite passed. Browser-computed light-mode pairs were
  foreground `#292d3a` on white (**13.72:1**), muted `#535c66` on white
  (**6.79:1**), and white on primary `#068667` (**4.55:1**).
- Raw and projected extension content is rendered as React text/`pre` content,
  not unsafe HTML.

The browser console contained **0 warnings and 0 errors** during the final
journey checks.

## Privacy, isolation, and architecture

- The UI consumes only Core's public task/receipt response.
- HTTP status is classified into bounded recovery states; arbitrary response
  detail is discarded and never becomes a rendered error message.
- Private prompts, resolver content, credentials, secret-like arbitrary
  metadata, and raw provider errors are not rendered.
- The Core public-contract tests verify recursive secret redaction, bounded
  output, and recommendation/decision/adoption separation.
- The extension preview contains only the user's bounded handoff fields and
  typed reference identities. It does not claim resolution before a receipt.
- Core's only Phase 6 product change is adding the neutral public `/tasks` and
  `/extension-invocations` paths to Canvas's existing development proxy.
- No Marketing name, route, presentation component, or policy was added to
  Core. Naked Canvas removed the wiring and still built and passed the leakage
  gate.

## Defects found and fixed

1. **Canvas could not proxy the live public APIs in supported local
   development.** Added neutral `/tasks` and `/extension-invocations` proxy
   routes.
2. **The receipt view omitted accepted public concepts.** Added retry actor and
   policy, lineage links, raw output, human decision, adoption, complete
   cancellation detail, and reference identities/statuses.
3. **Recovery failures were flattened into generic request failure.** Added
   typed not-found, unauthorized, invalid, transient/network, and unknown
   classifications with safe presentation and an explicit recovery action.
4. **Detail, URL input, and history could race during retry/poll transitions.**
   Made URL changes the retrieval trigger and refresh history on status changes.
5. **Duplicate rapid retry/cancel/launch actions were possible before React
   disabled the control.** Added an immediate action lock.
6. **Header, receipt input, sidebar, and mobile-menu targets were 32px.** Raised
   the shared Hub controls and menu items to a 44px minimum.
7. **Phase 5 UI tests covered launch but not Phase 6 recovery.** Expanded helper
   and Hub coverage to 24 focused tests.

## Verification commands and exact results

Final passing commands:

```bash
# Scratch wired Canvas using the supported one-line ext shim.
./node_modules/.bin/vitest run \
  ../../../extensions/b2b-marketing/ui/canvas/app/data/extension-invocation.test.ts \
  ../../../extensions/b2b-marketing/ui/canvas/app/B2BMarketingHub.test.tsx \
  --reporter=basic
# 2 files, 24 tests passed

./node_modules/.bin/vitest run --reporter=basic
# 61 files, 479 tests passed

./node_modules/.bin/tsc --noEmit
# passed

npm run build
# TypeScript + production Vite build passed; 7,455 modules transformed

# Core workspace
npm run build:naked
# naked TypeScript + Vite build passed; 7,382 modules transformed
# naked extension-leakage test: 1 file, 9 tests passed

uv run pytest \
  tests/test_extension_invocations_api.py \
  tests/test_task_public_contract.py \
  tests/extensions/test_task_actions.py \
  tests/extensions/test_product_extension.py \
  -q --tb=short
# 75 passed

# Marketing workspace, using Core's environment
PYTHONPATH=/Users/eamirian/Projects/ace-ext-b2b-marketing:/Users/eamirian/Projects/ace-core \
  /Users/eamirian/Projects/ace-core/.venv/bin/pytest \
  ace_ext_b2b_marketing/tests/test_reasoning_invocation.py \
  ace_ext_b2b_marketing/tests/test_orchestrator_registration.py \
  -q --tb=short
# 7 passed; one non-functional pytest-cache write warning in the read-only sandbox
```

The full wired suite includes the design-system enforcement suites, 16
development-proxy seam tests, 20 contrast tests, 36 route smoke tests, Core
Canvas tests, and every Marketing Canvas test. Focused and full commands were
rerun after the final fixes. No Python changed, so changed-Python Ruff was not
applicable.

The first scratch-harness diagnostics were intentionally excluded from the
passing totals: copying extension source into Core's `src/app/ext` incorrectly
put extension-owned color data in the kernel scanner's scope, and an early
supported-shim harness lacked its root `node_modules` resolution link. The
final 479-test run used the supported one-line registration shim, external
extension tree, shared dependency root, and Core proxy fixture.

During final reconciliation, a concurrent Marketing worktree edit changed the
Market Intelligence Studio link in `B2BMarketingToolMatrix.tsx`. Phase 6 did not
author or alter that edit. It was preserved, copied into the final wired
harness, and is included in the final 479-test and production-build results.

## Limitations

- Provider quality, provider latency, billing, and real credential behavior
  were not exercised because this work packet forbids live/metered calls.
- The browser fixture proves product behavior against the frozen public
  receipt contract; Phase 5 owns real restart/persistence conformance.
- Browser back/forward traversed existing receipt URLs in the local acceptance
  session; the no-new-POST invariant is additionally enforced by deterministic
  Vitest mocks.
- The Canvas extension-registration seam remains experimental.
- The wired main JavaScript chunk remains above Vite's 500kB advisory threshold
  (1,745.96kB, 510.06kB gzip); this pre-existing performance warning is not a
  Phase 6 correctness or accessibility failure.
- No Phase 7 workflow or acceptance claim is included.

## Final acceptance

**PASS.** History, public receipts, URL refresh/recovery, retry/cancellation,
prepared/live separation, mobile usability, keyboard/overlay behavior,
semantics, contrast, reduced motion, and privacy/isolation all pass the Phase 6
gate with deterministic evidence and without changing the v1 wire contract.
