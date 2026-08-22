# PI13 WS6 local candidate evidence v1

- Date: 2026-08-21
- Baseline: `origin/main` / `e9a53ae63d209a266dc8a5156b1afcd5c939dd08`
- Disposition: **locally verified candidate; not landed**
- Scope: WS6 (Atrium) only. This record does not claim a public release acceptance run or an ACE 1.2
  acceptance pass.

## What WS6 delivers

Three defects, each of which would have shipped.

### 1. The onboarding flow claimed the one capability the journey does not have

Stage 8 of the semantic onboarding ladder was labelled **"Activate continuous maintenance"** and
reached `complete` whenever the durable Builder session was `active`. Its `detail` string was literally
true -- "The durable Builder session is active" -- but an owner reads the label and the state together,
and together they asserted exactly what J6 proved absent. J6 (continuous update) is deferred to 1.3 and
is disclosed as a gap in the acceptance record and the CHANGELOG; the surface where owners actually form
the expectation said the opposite.

The stage is now **"Activate the domain"**, and on an active session it states: *"The durable Builder
session is active. Briefs are rebuilt when you ask; this release does not update them on its own."*

Held by `onboardingJourney.test.ts`: an active session's stage must not carry the word `continuous`,
and must disclose that Briefs are rebuilt on request.

### 2. Locality was prose, so the Connect surface could not be mounted from anything trustworthy

`ConnectLocalSources` existed and was tested, but nothing rendered it. Mounting it required the Atrium
to know which source groups hold evidence on the owner's machine, and the onboarding-profile contract
said so only in prose (`access_label: "Read-only local files"`). Matching on a label string is not a
basis for deciding whether a read needs authorization.

`IntelligenceOnboardingSourceGroupV1Alpha1` now carries `requires_authorized_root: StrictBool = False`.
It is additive and defaulted, so every existing profile stays valid and unchanged; it is a general
access property, so no Personal noun enters `ace/intelligence`. The shipped Personal profile sets it on
`personal_local_sources`.

The Atrium's parser fails closed: a `requires_authorized_root` that is present but not a boolean
rejects the whole source group rather than reading as "no authorization needed". The TypeScript field is
required, not optional, so no profile fixture can omit its authorization posture by accident.

### 3. Selection was being treated as consent

The Evidence step now blocks `Prepare exact plan` while any selected group that requires an authorized
root is unauthorized. Three states stay distinct, and only the third unblocks planning:

| State | What the owner did | Planning allowed |
|---|---|---|
| selected | chose the group | no |
| previewed | saw the exact scope ACE would read | no |
| authorized | allowed the read of that shown scope | yes |

Consent also does not outlive the scope it was given for. Deselecting a group withdraws its
authorization, because its Connect surface unmounts with the scope on screen; changing profile clears
all authorizations.

Held by `OnboardingPreview.test.tsx`: the surface renders for a group that declares the requirement,
`Prepare exact plan` stays disabled through selection and through preview, `onConnectAuthorize` is not
called until the owner allows the read, and only then does planning unblock.

## The finding that made the other three matter

`core/engine/atrium/static` is a **committed build artifact** -- it is what the Python package serves --
and nothing in the repository rebuilds it, checks it, or notices when it drifts. The committed bundle
contained no `personalJourneyApi` and no Connect surface, and still contained the string
`Activate continuous maintenance`. Every WS6 change above, and every Atrium change made in this
continuation before it, existed only in source.

Rebuilt with `npm run build:package`. Verified by grepping the new bundle for
`Show me what ACE would read`, `Allow ACE to read these files`, `Activate the domain`, and
`rebuilt when you ask` (each present once) and for `Activate continuous maintenance` (absent). Two
consecutive builds produced byte-identical output under the same content hashes, so the artifact is
reproducible from source.

CI now fails when the committed bundle does not match the source it is built from
(`.github/workflows/ci.yml`, "Fail if the committed Atrium bundle is stale"), with the fix named in the
error message. Without that gate the same silent staleness recurs on the next UI change.

## A second artifact defect, found by checking the wheel rather than the tree

Rebuilding the bundle is necessary but not sufficient. `setuptools` copies package data into
`build/lib/` and never prunes files that have since been deleted, so a locally built wheel carries every
Atrium bundle the tree has ever held. The first lane wheel contained both `index-Bua4tRJ5.js` (the old
bundle, carrying `Activate continuous maintenance`) and `index-YdGv59gM.js` (the new one) -- about two
megabytes of stale, unreferenced JavaScript. Behaviour was correct, because the packaged `index.html`
references only the new assets, but the retired claim shipped inside the artifact.

Removing `build/` before building produces a wheel with exactly the three current assets. CI publishes
from a fresh `actions/checkout` and so has no `build/` directory, which is why published artifacts were
never affected -- but any locally cut release would have been. Recorded in CONTRIBUTING alongside the
rebuild step.

The WS0 lane was then rebuilt from byte-clean wheels and re-run, so the evidence below rests on
artifacts containing only current bytes.

## Verification

- Canvas: 700 tests pass, `tsc --noEmit` clean.
- Python, CI-equivalent (`pytest -m "not e2e"`, the gate CI actually runs): **9636 passed, 50 skipped,
  4 failed** in 7m06s. The four are the documented baseline -- three in `tests/test_graph_context.py`
  and `test_extension_disabled_kernel_starts_without_live_composition` -- unchanged by this work. The
  count rose from 9633 by exactly the three tests added here (two pack-contract, one roadmap).
- The onboarding-profile resource projection legitimately gained the new field and its exact
  expectation was updated; the pack, installed-catalog, journey-start, local-source-connect-host,
  build-plan, and onboarding-API suites pass.
- WS0 lane, rebuilt from byte-clean wheels against an ephemeral SurrealDB: J1-J5 PASS, J6 BLOCKED as
  disclosed, J7-J10 PASS. The gate exits 1 because J6 is blocked; that is the disclosed gap, not a
  regression.

## Disclosed, not fixed

`tests/canvas/test_e2e_jtbd.py::test_jtbd_make_architecture_decision` fails locally: the canvas spec
generator writes `integration_points` as an array of strings into a SurrealDB field declared
`array<object>` (`core/engine/product/spec_generator.py:927`), which raises rather than normalizing.
It is pre-existing and untouched by this branch -- no file in that call path differs from `origin/main`
-- it is `e2e`-marked and therefore excluded from CI (`-m "not e2e"`), and it depends on a locally
reachable provider despite the module docstring claiming no real LLM is required. It is recorded here
because it is a real crash on a shipped route, not because WS6 caused it.
