# P1D1 shift-triggered PREPARED Brief

**Status:** local, candidate evidence verified on 2026-08-06 for the exact bounded route described
below, including the explicit synthesis-schema compatibility repair. This is a source-checkout
reproduction, not verification of a published artifact — no ace-core 0.4.1 git tag, GitHub Release,
or PyPI package exists yet. General P1D Brief synthesis remains open.

P1D1 adds one governed, route-triggered PREPARED path over the already-persisted P1B closure:

```text
one routed Signal → one Shift → its Entity Snapshots → their Observations
                                      ↓
                         one canonical PREPARED Brief
```

It does not promote the P1C2 LIVE Observation and creates no LIVE Signal, Shift, or Brief. It adds
no source capture, scheduling, Cases, Monitors, Subscriptions, delivery channel, Decision, Outcome,
feedback, UI, HTTP route, MCP tool, or Content-AI behavior.

## Synthesis schema compatibility repair

The first P1D1 candidate incorrectly changed the canonical meaning of
`ace.intelligence.synthesis/v1alpha1.required_sections` from the historical lexical normalization
to declaration order without changing the contract identifier. That candidate is rejected as a
schema/versioning break and is not the verified artifact.

The repaired boundary supports two closed-world contracts:

- `ace.intelligence.synthesis/v1alpha1` retains byte-for-byte legacy canonicalization. Required
  sections are normalized with the historical set-like lexical ordering, and runtime uses that
  sorted effective order without reinterpretation.
- `ace.intelligence.synthesis/v1alpha2` makes unique declaration order identity-bearing. The
  bounded P1D1 fixture opts into this contract for exact section-order validation and rendering.

Compiler dispatch, direct `CompiledModuleV1` revalidation, cross-module dependency validation,
runtime template resolution, public exports, and dependency-clean artifact probes support both
contracts. Unknown versions and canonical payloads cross-wired to the other contract fail closed.
The Core-local non-lexicographic legacy regression pins synthesis module digest
`sha256:99ccea5e5fe93cd2ad22c20e9a36d30ce61506f8f998bc30da1a0432947495c0`
and its minimized Pack `pack_ir:a61b41ffb771a06bfbbada096d09df6d` /
`sha256:a61b41ffb771a06bfbbada096d09df6d7a6ebb470ccd6d00ccdfd22e8dbd21bb`.
Reordered and duplicated `v1alpha1` declarations converge byte-for-byte; reordering the same
`v1alpha2` section declaration changes both module and Pack identity. Separately, the unchanged
external Market declaration compiles again to Pack `pack_ir:19de6d59b28095f7bd7600364c3b4de7` /
`sha256:19de6d59b28095f7bd7600364c3b4de787cce0365764cf54ab9f282f3412c2dd`.

## Ownership and trust boundary

Intelligence selects and validates the exact typed resource closure. It resolves exactly one
committed activation-bound synthesis template and persona set from exact Pack IR, treats every
source payload as untrusted data, validates the provider's structured draft against section,
claim, support, citation, explicit-inference, uncertainty, and recommendation policy, constructs
citations, and renders canonical markdown mechanically from validated claims. Provider prose and
provider-rendered markdown are never canonical.

Core remains domain- and Brief-blind. It freezes and revalidates the selected records as opaque
canonical context, resolves current actor-scoped capability and authority use, durably accepts the
exact request before provider execution, persists only structured final output plus content-free
selection/injection/provider-declared-output-reference receipts, rechecks authority and governed
heads after inference, commits terminal material atomically, and replays the exact terminal result
without a second provider call. Provider execution is at-least-once until the terminal transaction
commits; an accepted nonterminal attempt is orphaned and requires a new attempt key.

The shared PREPARED synthesis receipt contains exact typed-resource-to-opaque-Core-context
mappings, activation and Pack references, template/persona coordinates, section and claim/support
bindings, cited Observation-to-citation mappings, Core terminal/result references, an exact append
intent identity, and only an opaque final-write authorization reference. It contains no actor,
authenticated session/window, capability-use payload, authority/grant material, provider
instruction, evidence text, result JSON, hidden reasoning, or governed state head.

Full final-write capability, authority, session, grant, operation binding, subject, and use receipts
remain in Core's private receipt space. Intelligence receives the versioned safe projection
`{authorization_ref, authorized_at, state_preconditions}`. State preconditions are transaction
coordinates, not bearer authority. The private authorization is a durably accepted exact
`append_immutable_records` command whose subject is the versioned append intent binding the exact
two-record recipe. Expiry after acceptance does not rewrite that historical command, but its exact
governed-head preconditions must still match when the PREPARED append consumes it; this is not a
continuously current database-time authorization check.

## Exact append and recovery semantics

The append intent binds PREPARED record space, stable transaction-key derivation, exactly two
ordered records, kinds, contracts, record-key and payload/material-digest recipes, envelope times,
processing order, authorization-reference insertion, submitted-time derivation, semantic neutral
projections of both final payloads, and all intended governed-state identities. Intelligence
materializes the Brief and synthesis receipt at Core's final authorization time, revalidates every
recipe dimension, then atomically appends both records on the existing append-only substrate.

Core treats the caller key as an authorization family. After resolving current use, it derives the
private transaction identity from that family, exact action-request digest, authenticated-session
receipt and digest, operation-binding digest and head, every caller-required head, and the exact
resolved capability and authority heads. An exact retry under the same session and heads converges;
a renewed session or advanced capability/authority head creates a new inert private attempt without
poisoning the stable final Brief transaction key. Private capability/authority record keys are
scoped to that resolved attempt while their resolver-issued payload identities and evaluation
times remain truthful.

The Surreal adapter classifies a possible concurrent winner only by reloading and fully validating
the exact expected receipt once. An exact winner converges, a same-identity divergent winner is a
replay conflict, no winner preserves the original typed failure, and reload/revalidation failure is
a sanitized persistence error. This covers the preflight transition and CREATE-only collision
windows without error-string or partial-hash classification.

## Replay and current delivery

Historical verification reloads the exact activation commit referenced by the synthesis receipt,
resolves the full exact historical Pack reference through `CompiledPackArtifactResolver`, freezes
the selected resource closure again, reconstructs the exact historical Core reasoning request from
private acceptance material, and calls Core execution with a fresh same-principal delivery context.
Core first proves immutable request/acceptance/result/use/terminal closure, then resolves current
delivery capability and authority. A renewed valid policy head or grant may authorize delivery;
resolver denial, expiry, cross-product, or cross-principal context fails closed. Intelligence parses
the persisted Core `structured_json` as the source draft, reruns the same pure assembly function,
reconstructs and verifies the exact private append authorization and manifest, and compares the
two-record transaction before returning content. Replay invokes the provider zero additional times.

Historical Pack replay supports exact externally retained Pack IR through the resolver port. P1D1
does not add a durable multi-Pack archive, archive-before-activation invariant, catalog discovery,
or rollback store. Missing, wrong, or tampered Pack material fails before reasoning; successful
replay after Pack/activation/binding rotation requires the host to retain and resolve the old exact
Pack IR.

## Deterministic fixture and identity pins

The P1D1 domain-neutral price fixture permits only the persisted assertion: “The listed Edge X1
price changed from USD 1,200 to USD 1,080.” Its source locator remains `null`; no absent competitor
or relationship is attributed. The verified P1D1 result pins are:

| Material | Identity | Digest |
|---|---|---|
| P1D1 ordered Pack | `pack_ir:ccf7f4b72c91a549f42493002f1be1bc` | `sha256:ccf7f4b72c91a549f42493002f1be1bca1da1be5fe8fe8ae255ce30c801a7d7d` |
| P1D1 activation revision | `activation_revision:caeb8fcafd17a6ba50741d44837d9980` | `sha256:caeb8fcafd17a6ba50741d44837d9980f755549d82cabcdb64d127efab72fff0` |
| PREPARED Brief | `brief:52d3d753b9b2ee30d1a8faaa316e1652` | `sha256:52d3d753b9b2ee30d1a8faaa316e16526b3a6e5e4cf793d8417df8b91fe6a206` |
| synthesis receipt | `brief_synthesis_receipt:64f37fcb53080876222caf5f2d54eeea` | `sha256:64f37fcb53080876222caf5f2d54eeea7a521339963a421a08df47f06c409c16` |
| two-record append receipt | `append_only_receipt:a0f17f23345df62697e317b927484ef1` | `sha256:99e04efd57a75d092329c27e222e3c31fa0656c65bc0fb4a9ded1ca99891cd6b` |

P1D1 adds no fields or defaults to `BriefV1Alpha1` or `GroundedClaimV1Alpha1`. The historical P1B
fixture remains byte-for-byte pinned:

| Material | Identity | Digest |
|---|---|---|
| Observation 1 | `observation:f3218971b3706e0aaf58c726a1ed4186` | `sha256:f3218971b3706e0aaf58c726a1ed4186b819b936a94980b9115d93bce147620b` |
| Observation 2 | `observation:68187e5749282dec9d5975440178ead7` | `sha256:68187e5749282dec9d5975440178ead7a8312173b816be0cc014891a2f100f89` |
| Entity Snapshot 1 | `entity_snapshot:98318f7ab4bcf1ccc867e376795fe750` | `sha256:98318f7ab4bcf1ccc867e376795fe750801426567a6f0aa4655ec0da1d7a04f6` |
| Entity Snapshot 2 | `entity_snapshot:28becf0a1cb6ed9de8cf0e3cfb495caa` | `sha256:28becf0a1cb6ed9de8cf0e3cfb495caa4210d4041c7029c0ad9d2640f596cd50` |
| Shift | `shift:c85850298925941923343b22b6417332` | `sha256:c85850298925941923343b22b64173324cc97301ae3c61dec486aabe7cb035c8` |
| Signal | `signal:0ee66da80de462596b1807af27ccaab9` | `sha256:0ee66da80de462596b1807af27ccaab9f22fcd26c0f5d61ca17ebd78f1ff1a05` |
| historical Brief | `brief:363acc9e362149bc5c8b2fc843e39345` | `sha256:363acc9e362149bc5c8b2fc843e39345def7022399dfe73b853b27dc7549cb96` |

The P1A fixture remains at Pack `pack_ir:161356858f3bd64d914b9588db0c3efa` /
`sha256:161356858f3bd64d914b9588db0c3efa3f81190e6811b7c562fe62595a846003`,
activation revision `activation_revision:cbbceac63cfee2af00d64d9b63f2bf22` /
`cbbceac63cfee2af00d64d9b63f2bf22d5931a724dadcfcf8359e9571a8c01a5`, and commit
`governed_state_commit:dbb1ed0520769718a751717aafbf4ac7` /
`dbb1ed0520769718a751717aafbf4ac74cfb0743e090b2ba8f341fba2e603f60`.

The legacy Market synthesis module and full Pack identities above are pinned by a new upstream
non-lexicographic regression and the unchanged external Market suite. The P1C1 exact
numeric/categorical output pins remain those recorded in
[P1C1 evidence](platform-p1c1-declarative-source-mapping-v1.md), and the P1C2 ingress request,
use, snapshot, LIVE resource, admission, and append pins remain those recorded in
[P1C2 evidence](platform-p1c2-governed-live-source-ingress-v1.md). The complete Intelligence gate
and explicit P1C1 pinned-output test passed after P1D1.

## Verification record

- Focused governed reasoning/action authorization plus Brief synthesis:
  `uv run pytest tests/intelligence/test_governed_reasoning.py tests/intelligence/test_brief_synthesis.py -q --tb=short`
  — **51 passed**.
- Surreal failure-classification unit matrix:
  `uv run pytest tests/intelligence/test_runtime_use_and_preconditions.py -m "not integration" -q --tb=short`
  — **33 passed, 1 deselected**.
- Exact Core-local legacy non-lexicographic identity regression:
  `uv run pytest tests/intelligence/test_solution_pack_modules.py::test_legacy_nonlexicographic_synthesis_identity_is_byte_for_byte_stable -q --tb=short`
  — **1 passed**. It pins the legacy synthesis module and minimized Pack identities and proves
  reordered/duplicated `v1alpha1` declarations converge.
- Complete Intelligence suite: `uv run pytest tests/intelligence -q --tb=short` — **249 passed**.
- Unchanged external Market Pack compatibility smoke, using this worktree on `PYTHONPATH` without
  adding a repository dependency: `domain_packs/tests` — **71 passed, 1 skipped**. This includes
  the frozen full-Pack `pack_ir:19de6d59…` identity and durable P1B/P1C1/P1C2 conformance.
- Public boundary, build, artifact-contract, Intelligence MCP compatibility, and kernel group:
  **45 passed, 1 opt-in artifact test skipped**. The isolated frozen artifact-contract check was
  **1 passed**.
- Full dependency-clean wheel/sdist acceptance:
  `ACE_RUN_ARTIFACT_INSTALL_ACCEPTANCE=1 uv run pytest tests/test_artifact_install_acceptance.py::test_dependency_clean_current_wheel_and_sdist -q --tb=short`
  — **1 passed**. It verifies hash-pinned dependency inputs, exact source members, wheel/sdist
  fixed points, two fresh processes per artifact, dependency checks, extension isolation, privacy,
  public-import boundaries, and exactly 11 MCP tools.
- Repository Ruff: `uv run ruff check .` — **passed**. Diff whitespace check — **passed**. Kernel
  boundary: `uv run pytest tests/test_kernel_boundary.py -q --tb=short` — **4 passed**.
- Extension-disabled non-E2E regression:
  `ACE_DISABLE_EXTENSIONS=1 uv run pytest -m "not e2e and not requires_extensions" -q --tb=short`
  — **7,092 passed, 237 skipped, 263 deselected, 8 unrelated failures**.

The eight extension-disabled failures are baseline/environment failures outside this packet:

1. two canvas proxy tests cannot bind loopback ports in the managed sandbox;
2. the loopback egress-guard test cannot connect in the managed sandbox;
3. three grounded-state baseline tests assume `.git` is a directory and read `.git/HEAD`, while
   this checkout is a linked worktree with a `.git` pointer file;
4. the existing `ace_scan_repo` error test encounters sandbox ownership-resolution denial before
   its expected missing-path branch; and
5. the no-database startup test cannot bind an ephemeral loopback port in the managed sandbox.

No focused, Intelligence, P1A–P1C2 compatibility, public-boundary, artifact, MCP-count, Ruff,
diff, or kernel failure remains.

## Rejected pre-repair artifact

The pre-repair wheel exposed the same-contract `v1alpha1` ordering break and is rejected. Its
obsolete path and digest are intentionally omitted so it cannot be mistaken for a usable handoff.

## Repaired compatibility artifact gate

The dependency-clean current wheel/sdist acceptance passed after the schema split: **1 passed in
61.55 seconds**. It rebuilt from the exact source snapshot with hash-pinned inputs, installed and
probed both artifact forms in fresh processes, found both public synthesis contract families,
loaded zero private `core.engine` modules through the public `ace.*` boundary, and retained exactly
11 MCP tools.

- Corrected gate wheel: `/tmp/ace-p1d1-compat-handoff.IynPHl/ace_core-0.3.0-py3-none-any.whl`
- SHA-256: `6533effa59d2b12fbdd3540c46fa9410a2ec8b72330c20531e14bf3d0cd7d8a9`
- Size: `8,665,279` bytes
- Clean environment: `/tmp/ace-p1d1-compat-handoff.IynPHl/clean-venv`
- Clean dependency check: **157 packages compatible**.
- Installed-origin probe: both public synthesis contracts preserved their distinct sorted/ordered
  semantics; `ace.application`, `ace.core`, and `ace.intelligence` loaded from the clean
  environment; public imports loaded zero private `core.engine` modules.
- Installed MCP surface: exactly `ace_start`, `ace_load`, `ace_capture`, `ace_task`, `ace_status`,
  `ace_capture_idea`, `ace_search`, `ace_briefing`, `ace_impact`, `ace_history`, and `ace_related`.

The final post-evidence handoff wheel path and SHA-256 are reported outside this file to avoid
making an artifact contain its own digest.

## Scoped file manifest and inherited baseline

The inherited worktree was already dirty with completed uncommitted P1A/P1B/P1C1/P1C2 and
unrelated user work at HEAD `b41ee1d2f766b3046f579efcfa7a4e54d281090f`. The P1C2 evidence records
its earlier baseline snapshot as `/tmp/ace-core-p1c2-baseline-019fd828.status`, SHA-256
`a053a65ea637d5f2b10ec8200575495a57f2070f947f68209045fb0e433e6e49`. No new serialized
P1D1-start status snapshot was created before edits, so the following is the exact semantic P1D1
ownership manifest, not a claim that these paths were clean beforehand:

- `MANIFESTO.md`
- `ROADMAP.md`
- `docs/architecture.md`
- `docs/evidence/README.md`
- `docs/evidence/platform-p1d1-governed-routed-brief-v1.md`
- `ace/application/__init__.py`
- `ace/application/brief_synthesis.py`
- `ace/application/domain_activation.py`
- `ace/application/intelligence_ledger.py`
- `ace/core/__init__.py`
- `ace/core/reasoning.py`
- `ace/intelligence/__init__.py`
- `ace/intelligence/contracts/__init__.py`
- `ace/intelligence/contracts/pack.py`
- `ace/intelligence/contracts/synthesis.py`
- `ace/intelligence/packs/compiler.py`
- `ace/intelligence/packs/runtime.py`
- `ace/intelligence/synthesis.py`
- `core/engine/core/immutable_records.py`
- `evaluations/artifact_install_acceptance.py`
- `evaluations/fixtures/artifact_install_acceptance_v1.json`
- `tests/test_artifact_install_acceptance.py`
- `tests/intelligence/test_brief_synthesis.py`
- `tests/intelligence/test_governed_reasoning.py`
- `tests/intelligence/test_intelligence_boundaries.py`
- `tests/intelligence/test_prepared_intelligence_ledger.py`
- `tests/intelligence/test_runtime_use_and_preconditions.py`
- `tests/intelligence/test_solution_pack_modules.py`
- `tests/intelligence/test_pack_compiler.py`

No file was staged, committed, pushed, published, reset, stashed, overwritten, or discarded.

The exact compatibility-repair delta within that larger P1D1 ownership manifest is:

- `MANIFESTO.md`
- `ROADMAP.md`
- `docs/architecture.md`
- `docs/evidence/platform-p1d1-governed-routed-brief-v1.md`
- `ace/intelligence/__init__.py`
- `ace/intelligence/contracts/__init__.py`
- `ace/intelligence/contracts/pack.py`
- `ace/intelligence/contracts/synthesis.py`
- `ace/intelligence/packs/compiler.py`
- `ace/intelligence/packs/runtime.py`
- `ace/intelligence/synthesis.py`
- `evaluations/artifact_install_acceptance.py`
- `tests/intelligence/test_brief_synthesis.py`
- `tests/intelligence/test_solution_pack_modules.py`

The sibling Market repository was read only for its external compatibility smoke and was not
modified.

## Open limitations

P1D remains open beyond this one routed PREPARED closure. Scheduled and question-driven Briefs,
arbitrary frozen-context combinations, multiple Signals or Shifts, convergent DAGs, Cases and prior
Decisions, durable Pack archive/catalog discovery, a distinct read-result/read-Brief authority,
LIVE promotion, delivery channels, Decisions, Outcomes, feedback, and learning are not implemented
or claimed. Selection/injection/provider-declared output reference plus claim/support and explicit-
inference attribution does not prove causal or material influence; such a claim requires a separate
matched-control evaluation.
