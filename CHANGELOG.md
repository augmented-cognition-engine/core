# Changelog

Notable user- and contributor-visible changes are recorded here.

## Unreleased

### Supported

- Add the bounded `deliberation-receipt-v1` projection through existing task/status, CLI, thin
  client, and Living Product Graph reads. It records observable reasoning-shape selection,
  execution-identity-backed contributor artifacts, artifact-grounded conflicts, synthesis
  dispositions, and honest partial/degraded coverage without exposing hidden reasoning.
- Preserve the existing async task contract, I1 decision/correction and I3 intelligence-use
  receipts, and exactly eleven public MCP tools; no write or execution authority is added.

### Experimental

- Add the authenticated `extension-invocation-v1` HTTP envelope and
  `extension-invocation-receipt-v1` projection for extension-owned reference resolution and
  outcome projection over Core's durable task lifecycle. Failed or restart-degraded work resumes
  as a linked successor attempt, never as a fictitious continuation of a lost provider stream.
  This adds experimental HTTP execution authority but no CLI command or MCP tool; E1 remains not
  ready.
- Expand the experimental runtime with deterministic capability negotiation, schema discovery,
  product/user/workspace-scoped listing and attempt history, strict resolved-record provenance,
  idempotent concurrent resume, explicit retry policy/actor/reason lineage, cooperative
  cancellation states, output-contract validation hooks, immutable artifact references, and a
  provider-free reusable conformance helper. The shipped reference extension now registers the
  minimal `product:product-check` action.
- Harden the candidate Extension SDK with unambiguous tuple registration identities,
  registration-time action bounds, duplicate lifecycle rejection, self-validating public
  manifests, callable-free discovery, immutable-artifact conformance checks, an action handle
  returned from registration, and an independently executable scaffold conformance example.

### Migration

- Add schema v156 as one optional task receipt field and v157 as optional extension invocation,
  receipt, retry-lineage, cancellation, and retry-parent index fields without rewriting legacy rows.

### Known limitations

- Inspectable attribution is bounded final-artifact and execution evidence. It does not establish
  correctness, causality, benefit, decision quality, or access to hidden chain-of-thought.
- Extension task actions are trusted in-process code. Attempt-level resume is not distributed
  recovery or exactly-once external execution, and a complete receipt does not establish a
  correct or beneficial domain outcome.
- Cancellation is cooperative and process-local; it cannot undo completed provider calls or
  extension-owned external side effects. Capability negotiation and task actions remain
  experimental until the multi-package conformance/version-skew matrix is complete.

## 0.1.2

### Supported

- Add the versioned, authenticated, strictly read-only `ace landscape` journey for inspecting the
  Living Product Graph with stable identity, evidence, provenance, uncertainty, assertion history,
  deterministic ordering, bounded degraded behavior, and no change to the eleven-tool MCP surface.
- Complete I1 decision and correction inspection with structured evidence, assumptions,
  alternatives and reconsideration conditions; all four human dispositions; preserved
  supersession, invalidation, contestation and expiry; explicit incomplete provenance; fail-closed
  authorization, isolation and redaction; and restart-safe schema replay.
- Add the bounded `intelligence-use-receipt-v1` projection to existing task/status and Living
  Product Graph reads. It distinguishes retrieval, injection, reflection, and exact material I1
  decision deltas while preserving null, stale, invalidated, contested, harmful, mismatched, and
  failed comparisons.
- Preserve the public CLI and exactly eleven thin MCP tools. No new public write or execution
  authority is introduced.

### Provider and runtime

- Add the explicit ChatGPT-subscription Codex route with persistent `codex app-server` transport,
  `codex exec` compatibility mode, exact model/effort provenance, bounded structured output, and
  no automatic metered API-key fallback.
- Add process-wide provider admission control and task-level calls, tokens, latency, retry, route,
  and degraded-state accounting.
- Durable public task receipts now expose contributor and phase coverage in an `execution` block,
  including explicit partial-result attention without discarding usable output.

### Experimental

- Freeze the additive continuous-delta F1 foresight foundation: conditional forecast,
  intervention, indicator, outside-view, comparator-plan, structured-measurement, resolution, and
  proper interval-score contracts. These engine/HTTP surfaces remain experimental rather than a
  general 0.1.x compatibility promise.
- Add bounded interactive-output routing and advisory adaptive stage plans with inspectable route
  evidence; these do not add public MCP tools or unattended execution authority.
- Add the `ace.foresight.impact-evaluation/v1` L1 evidence gate. Its first checksum-frozen public-
  data probe is deliberately recorded as `benefit_not_established`; L1 remains candidate and F2
  remains gated.

### Fixed

- The experimental conflict workflow now persists product-scoped pending conflicts and
  quarantines both claims atomically, writes a durable attention signal, and returns provenance-
  bearing claims and resolution actions through the authenticated conflict API.
- API startup and the standalone schema installer share one audited historical-migration
  compatibility policy while migrations v142 and later remain fail-closed.
- Provider-selection tests now isolate explicit local subscription configuration, and roadmap
  projection tests no longer depend on rows in a developer database.

### Migration

- Add schema v143-v155 for conflict visibility, I1 decision/correction receipts, the F1 continuous
  foresight evidence chain, and the I3 intelligence-use receipt. Migrations are additive and
  existing public CLI/MCP identities remain unchanged.

### Known limitations

- L1 beneficial impact is not established: the current retrospective probe did not beat
  persistence, cluster-adjusted intervals include zero, and matched model-only plus verified
  intervention/confounder evidence are still required.
- F1, bounded adaptive routing, and the broader foresight HTTP engine remain experimental.
- Python 3.12 remains the supported interpreter, and the complete self-hosted Compose journey still
  uses a source checkout for pinned runtime assets.

## 0.1.1

### Supported

- Lead the public entry journey with one product-builder quickstart: bring a real decision,
  choose an existing model route, start the self-hosted runtime, and receive a recommendation.
- Keep advanced architecture, MCP, provider, extension, and manual-operation material available
  through progressive disclosure after the quickstart.

### Fixed

- Use concise outcome-led package metadata and absolute public links that continue to work when
  the README is rendered on PyPI.
- Make installed `ace setup --help`, missing-runtime guidance, provider selection, `ace doctor`,
  and service recovery point to concrete commands or public documentation without assuming
  repository knowledge.
- Include the R1 setup fixes for optional Discord configuration, Docker/Colima recovery, API log
  discovery, failed activation exit status, managed-process shutdown, and doctor recovery actions.

### Release maintenance

- Keep distribution, import package, engine, thin MCP client, reference extension, and public
  capability versions aligned at `0.1.1`.
- Default manual trusted publishing to `v0.1.1` and fail closed when a release tag does not match
  package metadata.

### Known limitations

- The complete self-hosted first-recommendation flow still uses a source checkout for its pinned
  Compose stack and local service scripts; the wheel provides imports and commands but does not
  silently download or provision runtime assets.
- Python 3.12 is the supported interpreter. R1 usability evidence is based on isolated AI-operated
  proxy trials rather than independent human testing, and model quality, capacity, and latency
  remain provider-dependent.

## 0.1.0

- Initial developer preview of the `ace-core` Python distribution, preserving the `ace` import
  package, `ace` CLI command, and version `0.1.0`.
- The supported public interaction boundary is the thin 11-tool MCP package and CLI.
- Atrium remains a separate experimental visual-product/research track and releases as public
  repository beta source while staying outside the Python wheel/sdist, golden path,
  supported-runtime claims, and supported release contract.
- The frozen `ace-preview-surface-v1` M2 scenario proved one durable preference survived restart
  and materially affected a later decision. Its matched-model evidence is n=1 and does not support
  a general superiority claim.
- Python packaging includes the kernel, CLI, thin MCP client, schema migrations, reference
  extension, evaluation material, public documentation, license, and notice while excluding
  Atrium beta source and local state.
- `ace doctor` validates a protected authenticated request and reports the effective provider-neutral
  model policy; `ace model-policy` exposes fast/capable/frontier mapping and degraded state.
- Supported Python is 3.12; the SurrealDB Python client is constrained to the compatible 1.x line.
- The heavyweight CodeSage/PyTorch embedding backend is now an explicit `codesage` extra; the
  default ONNX-backed install no longer pulls GPU/CUDA packages into the release container.

Release entries separate supported, experimental, fixed, security, migration, and known-
limitation notes.
