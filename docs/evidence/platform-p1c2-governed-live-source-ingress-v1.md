# Platform P1C2 governed LIVE source-ingress evidence

**Status:** local, candidate evidence verified on 2026-08-06. This is a source-checkout/local-wheel
reproduction, not verification of a published artifact — no ace-core 0.4.1 git tag, GitHub Release,
or PyPI package exists yet. P1D remains open.

P1C2 adds the smallest honest LIVE packet. For one exact immutable request, one current
authenticated actor may use one exact activation-bound, installed read-only adapter artifact to
capture one exact configured public HTTPS URI. ACE then atomically admits exactly these records, in
this order:

1. source-acquisition receipt;
2. canonical source snapshot;
3. one LIVE Observation;
4. its exact-lineage LIVE Entity Snapshot; and
5. LIVE source-admission receipt.

The packet creates no Signal, Shift, Brief, attention route, delivery, Decision, Outcome, feedback,
or learning event. A committed activation remains non-live until this separate bounded runtime-use
path succeeds.

## Public contracts and seams

- `ace.core.runtime_use` publishes `AuthenticatedRuntimeContextV1Alpha1`, exact capability-artifact
  identity, actor-scoped capability- and authority-use receipts, and the distinct
  `RuntimeUseResolver` protocol. Existing activation-time `CoreAuthorityResolver` is unchanged.
- `ace.core.state` publishes `GovernedStateHeadPreconditionV1Alpha1`; the append-only request and
  receipt carry a canonical unique tuple. Empty tuples serialize out, preserving every prior P1B
  identity byte-for-byte.
- `ace.core.source` publishes one exact `ResolvedSourceDefinitionV1Alpha1`, its resolver protocol,
  and the closed public-HTTPS URI validator.
- `ace.intelligence.contracts.source_acquisition` publishes the immutable ingress intent, adapter
  request/result, acquisition receipt, admission receipt, adapter protocol with explicit artifact
  identity, and host registry protocol.
- `ace.intelligence.interpret_live_source_mapping` is pure. It generalizes the already-resolved
  subject binding to PREPARED or LIVE without weakening or changing the P1C1 PREPARED interpreter.
- `ace.application.LiveSourceIngressService` composes activation reload, use-time resolution,
  host-registry adapter selection, capture validation, pure mapping, final re-resolution, atomic
  append, and exact reopen.
- `ace.testing.exercise_live_source_ingress_restart` lets an external pack prove commit, exact
  replay, and fresh-service replay using only installed public `ace.*` modules.

The public artifact inventory contains each of these members. Public `ace.*` imports load no
private `core.engine` implementation; production hosts supply the persistence adapter behind the
public Core port.

## Runtime authority and time boundary

The ingress request is content-derived and binds product, authenticated actor context, idempotency
key, exact `capture` operation, activation key, mapping, source-definition reference, compiled Pack
ID and digest, and request time. Both runtime-use receipts bind that exact request ID and digest and
also bind the operation explicitly. The capability receipt additionally binds the exact capability
contract, implementation ID/version, artifact digest, configuration reference, evaluation time,
and capability-state head. Its `capability_state_ref` is content-derived from that complete artifact
identity and must equal the head's state ID; an arbitrary same-kind head cannot satisfy the
contract. The service derives the same reference from the activation-bound artifact and supplies it
to both resolver passes. The authority receipt additionally binds the exact authority, grant
reference/hash, grant expiry, evaluation time, and grant-state head.

The service validates authentication at request construction, acquisition start, final resolver
pass, and immediately before append. It validates grant applicability at both resolver passes and
checks both the initial and final grant expiry against the final pre-append clock read. A receipt
whose evaluation is outside the authenticated window, a capture after authentication expiry, or a
slow final pass that reaches either authentication or grant expiry cannot commit. Runtime-use
receipts describe one past bounded use and expose `reusable_authority = false`; they are never
accepted as bearer tokens.

## Atomic governed heads and replay

The record transaction requires four independently current Core-governed heads:

| Head | What it closes |
|---|---|
| Domain Activation | retirement, revision, and binding changes |
| capability state | disable and exact artifact replacement |
| authority grant | revoke, expire/regrant, and grant-material changes |
| source definition | URI, source type, configuration, and subject-binding changes |

Each precondition binds state kind, product, state identity, exact sequence, revision ID, and commit
receipt ID. In-memory conformance and production SurrealDB enforce the same comparison. SurrealDB
reads every required `governed_state_head` after `BEGIN` and before any record `CREATE`; the records
and enclosing receipt commit in that transaction. P1C2 adds no schema migration because the
canonical receipt `payload_json` already persists and replays the preconditions. A test advances a
real head after append preflight but immediately before the database transaction; the transaction
fails with `ImmutableRecordPreconditionFailed` and persists no record or receipt.

Replay lookup precedes acquisition and head evaluation. Therefore an exact committed request
reopens historical admission after later retirement, disablement, revocation, expiry, or source
change without invoking the adapter. A reused idempotency key with different request material is a
conflict. Concurrent exact calls yield one commit and exact replays. An interrupted append leaves no
partial records or receipt. External acquisition is at-least-once until the atomic admission is
durable; failed attempts are not persisted in this packet.

The source-acquisition receipt deliberately does not name the eventual canonical snapshot. The
snapshot already binds the acquisition receipt, so adding the reverse reference would create a
content-identity cycle. The source-admission receipt similarly does not name its enclosing append
receipt.

## Source and network boundary

Alpha policy is one exact lowercase HTTPS URI, one exact source type and configuration, no URI
userinfo, fragment, credential, `secret_ref`, redirect, or alternate effective URI. Contract
validation rejects localhost, `.localhost`, `.local`, malformed numeric hosts, and non-global IP
literals. Adapter output must bind the exact capture request, preserve requested/effective URI
equality, report an empty redirect chain, provide canonical bounded JSON and its exact digest,
provide a locator and possible source/event times in valid order, list only global resolved IP
literals, and affirm that DNS-rebinding protection was applied.

This is deliberately not a network connector and performs no network access. Exact URI
authorization and obvious-host rejection are not a network-safety proof: any future network-capable
adapter is responsible for DNS resolution, validating every resolved and connected address as
public, and preventing rebinding before and throughout network use.

## Deterministic admission evidence

The frozen domain-neutral numeric fixture produces the following content identities:

| Material | Identity | Digest |
|---|---|---|
| immutable ingress request | `live_source_ingress_request:41b23ce1fc5910c80825df008c8ddd5d` | `sha256:41b23ce1fc5910c80825df008c8ddd5d06002303572ad137a11211a046752cf4` |
| capability use | `capability_use_receipt:9cc761de00e72fbcb0f95ae6efcdebb3` | `sha256:9cc761de00e72fbcb0f95ae6efcdebb30bf720acfa12d7ef729d5ed5d4ed2b0b` |
| authority use | `authority_use_receipt:e2ca1c963ca814d6fa99a998739fdbd2` | `sha256:e2ca1c963ca814d6fa99a998739fdbd2c6b9ab8e6d54d2dc97fc4b3e95457f95` |
| acquisition receipt | `source_acquisition_receipt:02d941fbad275b0ab095a53a6936c609` | `sha256:02d941fbad275b0ab095a53a6936c6095d5d731838a55c5c2c4840da3c45f5f9` |
| canonical source snapshot | `source_snapshot:9f80d395e6fc6bae483b61ce727edee0` | `sha256:9f80d395e6fc6bae483b61ce727edee049fde9e40ceb4fbd1eb8c0987a07a556` |
| LIVE Observation | `observation:bf86b75d56b09b6ee2f26e1e245de0ba` | `sha256:bf86b75d56b09b6ee2f26e1e245de0ba58d9fb70e9ee15bce84946afb9d154b7` |
| LIVE Entity Snapshot | `entity_snapshot:8e89aa7834e03d2c5f28d1a4460135ec` | `sha256:8e89aa7834e03d2c5f28d1a4460135ec38577c1b92360f4751abbb79b4d571a7` |
| admission receipt | `live_source_admission_receipt:f6c78802b749788318c63ef7aa6dc65a` | `sha256:f6c78802b749788318c63ef7aa6dc65a327255a91408be4a2858862a30e50b1b` |
| append receipt | `append_only_receipt:6539f9d1cd2b9fa9ee59ae1108415ae2` | `sha256:649e40cb549797a4a0d7466fb477b281eadc650f29f393b5a067d52a8132bbb1` |

The exact artifact-derived capability state is
`capability_state:8568e87b252bd9c64decde1e60f6ee07`. The other three frozen state
identities are `authority_grant:source-read`,
`domain_activation:7c5834546ef94567c4936e6930081266`, and
`source_definition:numeric`.

## Verification record

- Focused P1C2 runtime-use, atomic-precondition, LIVE mapping, service, race, boundary, and Surreal
  gate: **88 passed**.
- Complete Intelligence suite: **184 passed**.
- P1A/P1B/P1C1 activation, ledger, and mapping compatibility gate: **46 passed**; prior deterministic
  P1C1 pins remain unchanged.
- Artifact-contract/public-import preflight: **6 passed, 1 deselected**, plus an isolated public
  import probe.
- Dependency-clean wheel/sdist acceptance: **passed**. It verified 2 fresh wheel processes, 2 fresh
  sdist processes, exact installed origins, byte-identical source/installed critical members,
  fixed-point artifact reproducibility, disabled/enabled extension isolation, public imports with
  zero private `core.engine` modules, privacy canaries, dependency checks, and exactly 11 MCP tools.
- Repository-wide Ruff and diff checks: **passed**. Kernel boundary: **4 passed**.
- Extension-disabled non-E2E regression: **7,220 passed, 48 skipped, 263 deselected, 4 unrelated
  failures**. Three failures are the existing linked-worktree `.git/HEAD` assumption in
  `tests/test_grounded_state_runtime_baseline.py`; the fourth is the existing persistent Surreal
  collision for `specialty:test_arch_30201` in `tests/test_synthesizer.py`.

The dependency-clean build receipt is
`/tmp/ace-p1c2-final-019fd828/receipt.json`. The final task handoff reports the exact post-evidence
wheel path and digest; keeping the wheel's own digest out of this source file avoids a content-hash
cycle.

## Baseline-relative file manifest

The initial dirty-worktree baseline is `/tmp/ace-core-p1c2-baseline-019fd828.status`, SHA-256
`a053a65ea637d5f2b10ec8200575495a57f2070f947f68209045fb0e433e6e49`, at HEAD
`b41ee1d2f766b3046f579efcfa7a4e54d281090f`. P1C2 is bounded to exactly 27 paths.

These 20 paths already existed as dirty or untracked baseline material and were edited in place:

- `ROADMAP.md`
- `docs/architecture.md`
- `docs/evidence/README.md`
- `ace/application/__init__.py`
- `ace/core/__init__.py`
- `ace/core/records.py`
- `ace/core/source.py`
- `ace/core/state.py`
- `ace/intelligence/__init__.py`
- `ace/intelligence/contracts/__init__.py`
- `ace/intelligence/contracts/source_mapping.py`
- `ace/intelligence/source_mapping.py`
- `ace/testing/__init__.py`
- `ace/testing/immutable_records.py`
- `core/engine/core/immutable_records.py`
- `evaluations/artifact_install_acceptance.py`
- `evaluations/fixtures/artifact_install_acceptance_v1.json`
- `tests/intelligence/test_intelligence_boundaries.py`
- `tests/intelligence/test_source_mapping.py`
- `tests/test_artifact_install_acceptance.py`

These 7 paths were absent from the baseline and were added by P1C2:

- `docs/evidence/platform-p1c2-governed-live-source-ingress-v1.md`
- `ace/application/live_source_ingress.py`
- `ace/core/runtime_use.py`
- `ace/intelligence/contracts/source_acquisition.py`
- `ace/testing/live_source_ingress.py`
- `tests/intelligence/test_live_source_ingress.py`
- `tests/intelligence/test_runtime_use_and_preconditions.py`

No migration, staged file, commit, push, stash, reset, publication, or other checkout change belongs
to this packet.

## Precise Market P1C2 dependency surface

Market remains an external pack/application concern. To consume this packet without private Core
imports or lower-layer domain changes, it must provide only:

1. exact compiled Pack IR containing a closed source-mapping rule plus capability and authority
   declarations;
2. a current Core-committed ACTIVE activation binding that Pack, exact configuration, adapter
   artifact, and authority grant;
3. a Core-governed source definition binding one exact public HTTPS URI, source type, configuration
   digest, subject-binding ID, entity type, and entity reference;
4. a current authenticated actor/product context and an actor-scoped runtime grant for the exact
   `capture` request;
5. a separately installed, reviewed read-only adapter whose exact artifact identity is registered
   by the host and whose transport enforces the public-network/DNS contract; and
6. public `ace.testing` lifecycle conformance and its own domain fixture assertions.

The Pack's `allowed_uri_schemes` value is only a mapping constraint and is not source
authorization. Market may not use activation-time `ResolvedAuthorityGrantV1` as runtime authority,
may not call the PREPARED interpreter for LIVE material, and does not depend on a private
`core.engine` type.

## Explicit limitations

P1C2 supports one exact secret-free URI and fake/in-memory adapters in Platform tests. It has no
credentials, secret lookup, origin/path patterns, authorized redirects, network implementation,
failed-attempt ledger, adapter sandbox, entity-resolution service, catalog, delivery, reasoning,
or downstream intelligence promotion. The service-local concurrency lock does not turn acquisition
into an exactly-once external effect; durable admission is the exactly replayable boundary. These
are later additive slices, not implicit claims of this packet.
