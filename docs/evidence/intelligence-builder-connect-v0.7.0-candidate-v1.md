# ACE 0.7B Intelligence Builder Connect candidate evidence (v1)

**Status:** local stacked candidate above the 0.7A pack contract/compiler/conformance candidate in
draft PR #100. This record advances only Connect. It is not release evidence and does not claim
Map, Watch, Brief, Activate, the cumulative onboarding demo, independent consumer proof, or 0.7.0.

## Outcome

The public Python application surface can now discover two registered provider-free source
options, propose exact permission/scope/effect material, obtain Core-resolved human approval, run
one host-owned bounded connection test/sample, persist exact proposal and session handoffs through
Core's immutable record port, and reopen them from a fresh service instance.

The Connection Agent does not receive credentials, network access, connector configuration,
scheduling, delivery, pack activation, or grant creation authority. A returned connector sample
cannot change the approved connector, logical source identity, permission, scope, effect set, or
sample bound and still reach `sources_ready`.

## Exact provider-free reproduction

Two separate installed-wheel target directories reproduced the same terminal material:

| Material | Exact identity |
|---|---|
| option catalog | `source_option_catalog:389909681553b3dd524c13413abdfb65` |
| source-scope proposal | `source_scope_proposal:1940b57f8c3849ff1df0df0384d7fc68` |
| scope persistence receipt | `append_only_receipt:d6de3215bd191b0fc7da6e1cae8debab` |
| source-profile proposal | `source_profile_proposal:955a9a17fb262249248b0ad37dd3d4ca` |
| profile persistence receipt | `append_only_receipt:e585e4ca42d03893d9bec374194f2754` |
| reopened terminal revision | `intelligence_builder_session_revision:ce0db9d0d3a0d93e23fe01bdd7f389dd` |

The installed import resolved from the wheel target rather than the source checkout. Each run
returned two samples, `sources_ready`, and exact restarted scope/profile payload equality. The wheel
hash and target paths are build-environment evidence captured in the PR verification log rather
than a self-referential value embedded in package data.

## Failure controls

Focused tests prove:

- denied access calls no connector and durably blocks as `insufficient_permission`;
- a fresh service retries and resumes the same opaque session/correlation identity;
- stale source-scope handoffs fail before approval or connector use;
- scope widening and logical-source substitution cannot reach `sources_ready`;
- connector failure durably blocks as `failed_connector`;
- the Connection Agent cannot self-dispose the human/Core `sources_ready` transition;
- a stale session revision cannot fork the append-only chain;
- credentials, unsupported effects, scheduling, delivery, and authoritative configuration fail
  strict contract validation; and
- public contracts expose machine-readable JSON Schema with a closed effect enum and no credential
  field.

## Verification

- Connect unit and failure suite: **10 passed**.
- 0.7A compiler/conformance/activation, Connect, naked-kernel, exact eleven-tool MCP, package
  identity, and canonical narrative regression set: **111 passed, 1 expected extension-disabled
  skip**.
- README/roadmap/evidence label reconciliation: **20 passed** across the affected focused files.
- Full non-e2e gate with extensions disabled and three documented linked-worktree-incompatible
  baseline tests deselected: **7,505 passed, 50 skipped, 264 deselected**; the separate kernel
  boundary rerun added **4 passed**.
- `ruff`, `git diff --check`, and `uv lock --check`: passed before commit.
- installed-wheel run: passed from two independent target directories with exact identities above;
  built wheel SHA-256 was
  `0da78ee359523a325923584cbeb949bad842fae4788e8d424d567948ffdc2971`.

The full-suite audit also identifies three pre-existing baseline tests that read `.git/HEAD` as a
directory path and cannot run in a linked worktree, where `.git` is intentionally a file. They are
reported as environment-incompatible rather than changed in this bounded packet.

## Product and architecture fit

The public narrative now leads with “ACE, the Intelligence Builder. Build intelligence, not
infrastructure.” `MANIFESTO.md` remains the canonical vision and preserves the constitutional
Core/Intelligence/Domain Pack/connector boundaries. README and roadmap consistently expose Connect
→ Map → Watch → Brief → Activate, the five separate agents, honest current-versus-planned maturity,
and the 0.7A–0.7E sequence.

Domain Packs remain generated, governed, inert programs under the guided experience. 0.7B does not
invoke the pack compiler; the Activation Agent reuses the unchanged 0.7A boundary in 0.7E.

## Limitations and next packet

This provider-free slice profiles declared source shape only. Real connector discovery, transport,
credential UX, persistence adapters, product UI, source ingestion, Map, Watch, Brief, and Activate
remain separate work. A source profile is a proposal, not admitted LIVE evidence or authoritative
connector configuration.

The next bounded packet is 0.7C Map: the separate Ontology Agent and cited, editable concept-model
proposal. It may consume the exact source-profile handoff but may not acquire connector authority or
change 0.7B identities.

## Rollback

Stop composing the additive Connection Agent/application exports. Existing Core records remain
opaque immutable history. Rollback performs no connector operation, deletes no proposal, changes no
grant, and leaves 0.7A compiler/conformance/activation contracts untouched.
