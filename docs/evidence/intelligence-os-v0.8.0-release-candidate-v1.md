# ACE 0.8.0 Intelligence OS release candidate

Status: **candidate, pre-publication**

Candidate source base: `3415abfa5dd12ddd0a319a03ff0b61bd53d667c8`

Release branch: `codex/v0.8-release-acceptance`

## Claim

ACE 0.8.0 makes the released Intelligence Builder, governed composition, authorized memory,
action, outcomes, and feedback foundations consumable as one bounded Intelligence Operating
System. It does not claim managed operation, autonomous self-modification, general real-world
accuracy, or a hosted product.

The public contract is one authorized, point-in-time resource plane spanning Sources,
Connections, Observations, Entity state, Signals, Shifts, Cases, Briefs, Monitors, Subscriptions,
Agents, Decisions, Actions, Outcomes, Feedback, governed memory, and provenance. Atrium consumes
that plane as an optional repository-delivered workspace. Domain Packs remain inert; connectors
and trusted adapters remain the reviewed I/O and effect boundaries.

## Cumulative Core provenance

The release candidate is additive over public 0.7.0. The accepted mainline sequence is:

| Capability | Merge commit | Review |
|---|---|---|
| AM4 retention, export, and erasure | `bb7f4ba` | #126 |
| 0.8 architecture and legacy isolation | `c07dcab`, `0a7fade`, `15bfc23`, `18d0aef` | #127–#130 |
| Unified resource contracts and immutable projections | `bf4a75a`, `6b4d6b2` | #131–#132 |
| HTTP/API resource plane | `794183b` | #133 |
| Monitors and subscriptions | `cf53360` | #134 |
| Decisions, outcomes, and feedback | `5003cfb` | #135 |
| Sources, agents, memory, and actions | `3f4157e`, `8f54d89`, `8e155e0`, `6ce115b` | #136–#139 |
| Atrium Intelligence OS workspace | `c97b866` | #140 |
| Cross-domain resource correction | `3415abf` | #141 |

The schema head remains v177. The thin MCP surface remains exactly eleven HTTP-only tools. No
World or Market noun, source, policy, or product branch was copied into Core.

## Independent domain proof

### World Intelligence

- Repository: `augmented-cognition-engine/domain-world-intelligence`
- Accepted PR: #22
- Merge: `8e3343dbb1e1ae89a3407983ae1a5cfb521dd6d6`
- Result: an official-source LIVE Case is queried through the public plane across Observation,
  Entity, Signal, Shift, Case, Brief, Decision, Action, Outcome, Feedback, Source, and Connection.
- Restart/reopen identity is exact. Internal source-only evaluation controls remain explicitly
  degraded rather than receiving invented lineage.
- Candidate suite: **136 passed, 1 pre-existing skip**; GitHub CI passed before merge.

### Market Intelligence

- Repository: `augmented-cognition-engine/domain-market-intelligence`
- Accepted PR: #5
- Merge: `6132e2c244502a04bb106a3d58212262b6b83069`
- Result: an independent competitive-price PREPARED Case is queried through Observation, Entity,
  Shift, Signal, Case, Brief, Decision, Outcome, and Feedback.
- The analyst's `no_action` disposition is preserved; no Action is fabricated. Feedback remains
  non-live and produces no delivery or external effect.
- Candidate suite with World present: **135 passed, 1 optional pre-existing skip**; GitHub CI passed
  before merge.

These are domain-neutrality and product-contract proofs, not claims that either domain is complete
or that generated intelligence is generally accurate.

## Atrium acceptance

Atrium is a briefing-first workspace with first-class Intelligence, Opportunities, Agents,
Connections, and Strategy. Work is downstream. Ask ACE ranks only authorized resource records and
cites exact revisions. The accepted #140 gate covered **294 Canvas tests**, a production build,
desktop and mobile Playwright journeys, keyboard operation, screen-reader semantics, and explicit
empty, partial, and degraded states. Core GitHub Canvas checks also passed after the cross-domain
correction.

Atrium remains optional repository source, not part of the Python wheel and not a second durable
state, policy, or authority path.

## Package candidate

Candidate identities:

- `ace-core==0.8.0`
- `ace-reference-workspace-action==0.4.0`
- adapter dependency: `ace-core>=0.8.0,<0.9`
- unchanged adapter implementation artifact: `ace.workspace_action.reference/v0.1.0`

A clean isolated Python 3.12 environment installed the exact Core and adapter wheels together. It
reproduced Core and thin-client version `0.8.0`, adapter version `0.4.0`, the 22-kind
`IntelligenceResourceKind` contract, `IntelligenceResourcePlaneService`, and these exact eleven
HTTP-only MCP functions:

`ace_start`, `ace_load`, `ace_capture`, `ace_task`, `ace_status`, `ace_capture_idea`, `ace_search`,
`ace_briefing`, `ace_impact`, `ace_history`, `ace_related`.

Final tag-built hashes and public-index reproduction belong in the post-publication closeout. They
cannot be embedded in the tagged artifact that they hash without creating a self-reference.

## Verification

The accepted cross-domain Core correction at `3415abf` passed:

- regular Core gate: **7,904 passed, 48 skipped, 249 deselected**;
- naked-kernel gate: **7,890 passed, 50 skipped, 261 deselected**;
- kernel boundary: **4 passed**;
- all required GitHub checks: Lint, Tests, Naked kernel, Canvas, Security, and Docker.

The release-only version, roadmap, workflow, package identity, and reference-adapter focused gate
passes **33 tests**. The release branch's regular cumulative gate passes **7,904 tests**. Its naked-
kernel rerun reproduced one known transient Surreal transaction collision after **7,889 passes**;
the exact failed forget test passed immediately in isolated retry. The independent GitHub naked-
kernel job remains the publication authority: a reproduced failure stops the release. No green
state is inferred from this candidate document.

## Authority and rollback

- Feedback can propose a governance change but cannot select or apply it.
- Domain Packs cannot perform I/O, persist authoritative state, widen authority, or execute effects.
- Atrium cannot bypass product scope, entitlement, evidence admission, or action review.
- Public resource projections are rebuildable from authoritative Core records.
- Rollback is the last public `v0.7.0` artifact plus the independently versioned domain packages;
  0.8 data/schema compatibility must be assessed before any production downgrade.

Publication requires a green release PR, an exact main tag, trusted GitHub publication, public
artifact installation, and a separate closeout that records the immutable tag, workflow, hashes,
and checkout-free reproduction.
