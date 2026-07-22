# ACE capability evolution roadmap

This roadmap describes how ACE can become easier to teach, extend, and trust without changing its
identity into a general-purpose autonomous agent. It is capability-led: the useful outcomes are
graph-native procedural learning, reviewable evolution, efficient capability discovery, and safe
execution—not parity with another product or growth in tool count for its own sake.

This document is a companion to the [public roadmap](../ROADMAP.md). The public roadmap remains the
authority for outcome state and dispatch. Nothing here advances an outcome to `ready`, `active`, or
`passed`, and the current onboarding spine remains ahead of this work.

## Product thesis

ACE should let a user teach it a repeatable way of reasoning, inspect exactly what it learned,
approve an immutable revision, observe where that cognition component was used, and improve it from
measured outcomes.

```text
teach → propose → inspect → approve → use → measure → revise or retire
```

The Living Product Graph remains the system of record throughout that loop. A learned recipe,
framework, or instrument is not merely a mutable prompt file: it has identity, sources, provenance,
approval, revisions, executions, artifacts, outcomes, and conflicts.

### Vocabulary

- A **capability** is an outcome ACE can provide. The composer assembles capabilities from
  meta-intelligences, recipes, instruments, frameworks, tools, perspectives, and retained context.
- A **meta-intelligence** is a named kind of intelligence the composer can select for a problem.
  The current internal class is `MetaSkill`; that implementation name does not define the product
  vocabulary.
- A **recipe** is the phased orchestration that realizes a meta-intelligence. It is the canonical
  artifact for a repeatable reasoning process.
- An **instrument** is a reusable operation inside a recipe phase. A **framework** shapes how a
  phase reasons. A **tool** provides an external capability.
- A **learning proposal** is the graph object created by `ace learn`. Review determines whether it
  should create or revise a recipe, instrument, or framework.
- A **recipe revision**, **instrument revision**, or **framework revision** is an immutable,
  approved definition of that cognition component.

“Skill” remains a legacy implementation term in the older CRUD/selector/executor path and schema.
That path should converge into cognition recipes rather than becoming a second public abstraction.

## Guardrails

- **Propose before activation.** Generated recipes, instruments, and frameworks never become active
  merely because a task completed or a model suggested a change.
- **Evidence before confidence.** Repetition, accepted corrections, execution results, and observed
  outcomes support a proposal; model confidence alone does not.
- **Immutable revisions.** Approval activates a new revision and preserves the old one. Updates do
  not silently overwrite history.
- **Graph-native lifecycle.** Files may carry large instructions, scripts, templates, or assets,
  but the graph owns identity, hashes, provenance, scope, approval, and lifecycle state.
- **Progressive disclosure.** Classification and composition see compact capability metadata first;
  full definitions and supporting material load only after selection.
- **Explicit authority.** Reasoning, writing, local execution, remote execution, and promotion are
  separate authority levels with separate receipts.
- **No public-contract sprawl.** The 0.1.x thin MCP surface remains exactly eleven tools. New journeys
  use the CLI and existing capture, briefing, task, and status semantics until a later compatibility
  decision explicitly changes the contract.
- **Kernel remains domain-neutral.** Domain recipes, instruments, frameworks, tools, and vocabulary
  attach through the extension boundary. The kernel supplies lifecycle, policy, provenance, and
  execution contracts.

## Existing foundation

This roadmap extends implemented foundations rather than starting a parallel subsystem:

- problem-derived meta-intelligence selection and cognitive composition;
- Python- and YAML-authored phased recipes;
- instruments, frameworks, tools, depth gates, and orchestration patterns inside recipe phases;
- extension-owned recipe registration and classification routing;
- evidence-based self-optimizer proposals in the legacy learning path;
- explicit proposal approval and dismissal;
- failure memory, reasoning receipts, approval records, and outcome/calibration paths;
- MAKE/SHIP arms and workspace execution primitives behind experimental boundaries.

Those parts are not all compatibility-stable or joined into one supported journey today. The work
below closes that gap in dependency order.

## Reasoning evidence is product infrastructure

A strong demonstration needs visible decisions, disagreement, human correction, durable context,
and later material use because ACE itself needs those capabilities. They are not video-specific
instrumentation. The public backlog separates them into three outcomes so implementation can be
evaluated across real tasks, failure modes, and providers rather than against one signature
scenario.

### I1. Durable decision and correction records

**Outcome:** A user can inspect what was decided or corrected, who supplied or accepted it, what it
applies to, and when it should be reconsidered.

Required behavior:

- give decisions and corrections stable product-scoped identities;
- connect a decision to its originating task, selected option, scope, explicit assumptions,
  alternatives, evidence references, and reconsideration conditions;
- record human disposition (`accepted`, `edited`, `rejected`, or unresolved), actor or actor class,
  authority, rationale, surface, timestamp, and policy version where applicable;
- link a correction to the affected decision or context and preserve supersession, invalidation,
  contestation, and expiry without deleting history;
- expose content hashes and bounded provenance while protecting credentials, private task text, and
  unrelated retained intelligence;
- extend existing CLI, task/status, capture/load, and read contracts without adding a twelfth thin
  MCP tool or new execution authority.

Acceptance evidence:

- a fresh invocation after process restart retrieves the same decision/correction identities and
  relationships;
- acceptance text embedded in prose is never substituted for a structured human disposition;
- product-isolation, authorization, redaction, supersession, and invalidation tests fail closed;
- incomplete provenance remains explicit rather than being reconstructed from internal logs.

**Closeout (2026-07-22): passed.** The supported task/status/capture/load journey now covers the
complete decision context, all four dispositions, correction supersession/invalidation/
contestation/expiry, authorization and product isolation, credential redaction, explicit missing
provenance, and schema-zero-to-v145 replay on SurrealDB 3.1.4 and 3.2.1. The thin MCP surface
remains exactly eleven tools and gains no execution authority. See
[`decision-correction-receipts.md`](decision-correction-receipts.md) for evidence and limitations.

### I2. Attributable deliberation and synthesis

**Outcome:** A user can see why ACE selected a reasoning shape, which bounded positions materially
disagreed, and how the synthesis resolved or preserved that disagreement—without access to hidden
chain-of-thought.

Required behavior:

- retain bounded classification signals and perspective/stage selection reasons tied to observable
  task characteristics;
- represent each contributor with a concise position artifact: recommendation or claim, explicit
  assumptions, evidence identifiers, confidence/gaps, and execution status;
- identify decision-relevant conflicts among position artifacts rather than inferring disagreement
  from role labels;
- record which positions or evidence the synthesis accepted, rejected, preserved as contested, or
  used to bound the final decision;
- surface missing contributors, timeouts, tainted phases, partial coverage, and degraded synthesis;
- keep model scratchpads, private reasoning tokens, and unrestricted transcripts outside the
  public contract.

Acceptance evidence:

- generated persona labels alone receive no attribution or disagreement credit;
- at least one independent, pipeline, team, and adversarial path produces portable bounded receipts
  with honest partial/failure behavior;
- the final decision can be traced to contributor artifacts and evidence IDs without exposing
  chain-of-thought;
- provider or extension failures cannot be rendered as complete deliberation.

### I3. Inspectable continuity and material intelligence use

**Outcome:** A user can tell which retained intelligence entered later reasoning and whether it
changed the decision, while ACE preserves null, harmful, stale, contested, and degraded outcomes.

Required behavior:

- record stable intelligence IDs and the distinct states `retrieved`, `injected`, `reflected`, and
  `decision-material` rather than treating retrieval as use;
- name the receiving component or stage and preserve validity, relevance, trust, and provenance;
- compare compatible with-context and without-context decisions through exact structured field
  deltas, with matched provider/model/configuration conditions or an explicit degraded result;
- distinguish material influence from beneficial impact; connect benefit claims to later observed
  outcomes under L1;
- preserve continuity across a real supported runtime restart and fresh client invocation;
- retain route, exact model, calls, tokens, latency, retries, billing semantics, failures, and
  degraded states needed to interpret the effect;
- make irrelevant, null, invalidated, stale, contested, and harmful retained intelligence
  reproducible first-class evaluation cases.

Acceptance evidence:

- mentioning a remembered identifier without a structured decision change receives no materiality
  credit;
- matched controls support only the scoped memory-effect claim; cross-model differences are never
  used as causal evidence;
- the same receipt contract represents material, null, harmful, invalidated, mismatched, restart,
  failure, and degraded cases;
- a read-only supported surface can render the path from retained source identity to exact decision
  delta without reconstructing missing lineage.

### Product/evaluation boundary

I1–I3 own durable identities, provenance, bounded reasoning artifacts, lineage, materiality
semantics, and supported read behavior. Private evaluation tooling may freeze scenarios, provision
disposable product state, run raw-model controls and ablations, blind reviewer labels, compute
scorecards, hash evidence packets, or render a recording. Those tools test ACE; they are not new ACE
product capabilities and must not widen the eleven-tool contract.

Roadmap fit: I1 follows the developer-preview golden path and stable read contracts. I2 and I3
depend on I1; I3 also depends on R3 route evidence. I1–I3 support later E1, B1, and L1 work, but a
demonstration does not pull them ahead of R1–R4 or promote Atrium into the supported path.

## Capability sequence

### 0. Converge the cognition model

**Outcome:** ACE has one canonical path for composing and evolving reusable cognition before a new
teaching experience depends on it.

Scope:

- make the cognition recipe path the canonical representation of phased reasoning;
- map or retire the separate legacy `Skill`/`Job`/`Phase` selector and executor rather than
  exposing it under a new name;
- preserve compatibility for existing records and callers through an explicit adapter or migration;
- reconcile `org` remnants with product-scoped ownership;
- distinguish stable recipe, instrument, and framework identities from immutable revisions;
- define core, extension, product, and intentionally global scopes;
- align the recipe schema, composer, executor, registry, APIs, CLI, seed data, and migrations;
- add round-trip and migration tests that exercise the canonical representation through every layer.

Acceptance evidence:

- one canonical recipe representation survives create, read, compose, execute, revise, and reload;
- legacy records either migrate deterministically or fail with an actionable diagnostic;
- product isolation and intentional global cognition sharing have explicit tests;
- no change to the eleven-tool thin MCP contract.

Roadmap fit: prerequisite to **E1** and any learning capability; it must not displace **R1–R4**.

### 1. Teach and propose

**Outcome:** A user can turn a conversation, prior task, correction, document set, or described
reasoning workflow into an inspectable learning proposal.

Candidate CLI journey:

```text
ace learn "how we evaluate pricing experiments"
ace learn --from-task <task-id>
ace learn --from-path ./docs/release-process
ace learning proposals
ace learning show <proposal-id>
```

Required behavior:

- resolve and fingerprint every source rather than copying it into untraceable prompt context;
- separate sourced statements from inferred changes;
- classify the proposal target as recipe, instrument, framework, or no durable learning;
- produce a bounded draft using the canonical schema for that target; recipe drafts include
  activation signals, phases, instruments, tools, depth gates, outputs, and success measures;
- validate referenced tools, frameworks, extensions, and authority requirements;
- persist a proposal with source edges, model/provider route, prompt or policy version, timestamps,
  and validation results;
- make proposal creation idempotent for the same source set and intent;
- expose degraded extraction or missing-source states instead of fabricating completeness.

Acceptance evidence:

- the same sources reproduce the same proposal identity under the documented idempotency rule;
- every material draft element can be traced to a source or is marked as inference;
- malformed or unsafe cognition changes remain proposals and cannot enter composition;
- a fresh invocation can retrieve the proposal and its sources.

Roadmap fit: begin only after the onboarding and golden-path dependencies permit **E1** work.

### 2. Inspect, approve, and version

**Outcome:** A reviewer can understand and govern exactly what ACE is about to learn.

Candidate CLI journey:

```text
ace learning diff <proposal-id>
ace learning approve <proposal-id>
ace learning reject <proposal-id> --reason "..."
ace recipes history <recipe-slug>
ace recipes rollback <recipe-slug> --to <revision-id>
```

Required behavior:

- render a type-aware semantic diff; recipe diffs cover phases, instruments, tools, authority,
  activation, depth, outputs, and success measures;
- record approver identity, rationale, scope, and policy version in a durable receipt;
- materialize approval as a new immutable typed revision and move the active pointer atomically;
- preserve rejection, supersession, deprecation, and rollback history;
- quarantine conflicting proposals instead of resolving them with last-write-wins;
- surface pending reviews through existing briefing and attention mechanisms.

Acceptance evidence:

- unapproved revisions are never selectable;
- approval and active-pointer movement cannot partially succeed;
- rollback restores selection behavior without deleting later history;
- conflicting active revisions fail closed and create durable attention;
- all state remains inspectable after process restart.

Roadmap fit: depends on **I1** approval receipts and stable read contracts; contributes to **E1**.

### 3. Discover and load progressively

**Outcome:** ACE can grow a large cognition ecosystem without placing every recipe, instrument,
framework, tool schema, or reference into every model call.

Discovery levels:

```text
Level 0  identity + type + description + scope + activation + trust/effectiveness summary
Level 1  selected recipe revision + phases + instruments + authority + tool dependencies
Level 2  referenced instructions, templates, scripts, assets, and source evidence
```

Required behavior:

- search compact cognition metadata using task classification, product scope, explicit policy, and
  learned effectiveness signals;
- record which candidates were considered, selected, rejected, or unavailable;
- load only active approved revisions through the composer and recipe loader;
- enforce context and cost budgets with observable truncation or omission;
- degrade safely when an extension, referenced artifact, or tool dependency is unavailable;
- keep selection provider-neutral and independently testable.

Acceptance evidence:

- matched tasks materially use the selected recipe in a fresh invocation;
- irrelevant cognition components do not inflate prompt context beyond a documented bound;
- missing dependencies are visible in the receipt and cannot be mistaken for successful use;
- fixed-roster, no-capability, and selected-capability evaluations are reproducible.

Roadmap fit: strengthens **E1** and prepares **E2** without widening the public MCP contract.

### 4. Measure, revise, and retire

**Outcome:** ACE knows whether an approved recipe or component helped and can propose evidence-backed
changes without silently rewriting itself.

Required behavior:

- link every use to the exact recipe, instrument, and framework revisions, task, composition,
  model/provider route, tools, artifacts, cost, latency, failures, and outcome identity;
- distinguish completion, user acceptance, artifact quality, and real-world outcome;
- compare revisions only over compatible task cohorts and make uncertainty visible;
- detect repeated corrections, failure patterns, unused phases or instruments, and successful
  adaptations;
- create a new revision proposal with a bounded rationale and supporting executions;
- recommend deprecation when a cognition component is harmful, stale, unused, or superseded;
- calibrate proposal thresholds from approval and observed-outcome history without treating
  popularity as truth.

Acceptance evidence:

- evaluation can show where a revision helped, hurt, or remains unproven;
- later reasoning materially uses an accepted correction after a fresh invocation and restart;
- rejected changes do not leak into active execution;
- the system can report “insufficient evidence” without forcing a ranking;
- revision and retirement recommendations retain complete provenance.

Roadmap fit: the procedural-learning expression of **L1**; depends on stable outcome identity and
calibration evidence.

### 5. Execute through explicit adapters

**Outcome:** An approved decision and composed reasoning result can produce attributable changes
inside a bounded workspace, then pass through independent SHIP review.

Initial adapter sequence:

1. read-only inspection;
2. local workspace with an explicit writable root;
3. isolated container workspace;
4. remote or managed adapters only after portability and recovery guarantees exist.

Required behavior:

- declare required authority and side effects before execution;
- separate irreversible blocks, deterministic policy checks, human approval, and optional model
  risk assessment;
- resolve exact targets before mutation and retain before/after evidence;
- isolate credentials and record only references or approved metadata, never secret values;
- support cancellation, timeout, partial failure, replay identity, and cleanup semantics;
- route produced artifacts through SHIP security, testing, observability, operations, and scale
  challenges before promotion;
- retain executor, environment, commands or tool calls, diffs, verification, and promotion receipt.

Acceptance evidence:

- no write occurs without the required authority and receipt;
- local and container runs produce equivalent task identity and comparable evidence;
- partial execution cannot be represented as successful promotion;
- a restart leaves an honest recoverable, failed, or degraded receipt;
- SHIP can block promotion without erasing useful MAKE artifacts or execution history.

Roadmap fit: **B1**, then **E2**. It depends on **I1** and stronger **T1** guarantees.

### 6. Extend reach without moving the core boundary

**Outcome:** Users can trigger and receive ACE work through additional environments without making
messaging, scheduling, IDEs, or remote compute part of the reasoning kernel.

Possible extension-owned adapters include scheduled jobs, IDE protocols, messaging systems,
webhooks, and remote execution services. Each adapter must translate into the same authenticated
task, approval, receipt, product-scope, and delivery contracts.

Acceptance evidence:

- adapter removal leaves the kernel and retained intelligence intact;
- identity, authorization, product scope, and approval semantics match the supported CLI/MCP path;
- retries do not duplicate consequential work;
- adapter-specific failures do not corrupt canonical task or graph state;
- at least one external extension passes published conformance tests before ecosystem claims expand.

Roadmap fit: **H1** and **E2**, after tenancy, recovery, authority, and portability guarantees.

## Graph lifecycle

The minimum graph shape should make learning inspectable without forcing large artifacts into the
database. A proposal can target a recipe, instrument, or framework; the recipe path is shown here:

```text
task / correction / document / decision
                  │
                  └── derived_from ──> learning_proposal
                                           │
                                  approved_as / rejected_as
                                           │
                                           v
recipe ── active_revision ──> recipe_revision ── supersedes ──> recipe_revision
                                  │
                                  ├── composed_in ──> reasoning_run ── produced ──> artifact
                                  │                        │
                                  │                        └── evaluated_by ──> outcome
                                  │
                                  └── contains / requires ──> phase / instrument / framework / tool
```

Large scripts, templates, references, and assets may live in an extension package or content-
addressed artifact store. Their graph records retain hashes, locations, ownership, trust, and the
revision that approved them.

## Deliberate non-goals

- Replacing typed graph memory with flat personal-memory files.
- Letting the model freely edit active recipes, instruments, or frameworks by default.
- Treating one successful task or five tool calls as sufficient evidence of learning.
- Creating a third “procedure” abstraction alongside recipes and the legacy skill path.
- Renaming the legacy skill engine while preserving its duplicate selector and executor.
- Building a large messaging gateway into the kernel.
- Maximizing built-in tool count or exposing the experimental engine tool surface publicly.
- Making remote execution or unattended automation part of the first learning milestone.
- Claiming self-improvement without matched evaluations and observed outcomes.
- Creating a second extension system or allowing extensions to reverse the kernel dependency.

## Recommended dispatch

1. Complete the active **R1/R3** evidence spine and unlock **R4** according to the public roadmap.
2. During **E1** planning, converge the legacy skill path into cognition recipes and freeze the
   migration contract.
3. Deliver one narrow vertical slice: teach from an existing ACE task, classify the learning as a
   recipe change, inspect provenance, approve an immutable recipe revision, compose it in a fresh
   invocation, and record its use.
4. Add document/path learning only after source fingerprinting and degraded-state behavior pass.
5. Connect executions to outcomes under **L1** before enabling automated revision proposals broadly.
6. Add the first writable execution adapter only under **B1**, after approval and recovery contracts
   are stable.

The signature capability is not autonomous recipe writing. It is a trustworthy, reproducible chain
from experience to an approved cognition revision to measured outcome—and back to an inspectable
next proposal.
