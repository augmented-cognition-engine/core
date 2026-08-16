# ACE governed Code Intelligence improvement loop v1

Status: **ACE 1.1 target contract; subordinate to the public roadmap, product vision, Core
manifesto, and current 1.0 public architecture**

This document freezes how Code Intelligence detects incomplete changes, proposes reusable
architecture, and improves future coding-agent composition without collapsing repair, refactoring,
learning, and authority into one autonomous self-modification loop. It adds no current capability
claim. Release maturity and dispatch remain owned by the [public roadmap](../../ROADMAP.md).

## Decision

Code Intelligence is the first rigorous proof of ACE's governed improvement architecture because a
software system provides exact identities, dependency relationships, diffs, executable checks,
review, releases, and later operational outcomes.

ACE will implement three separately governed loops:

```text
1. Complete the current change
   verify → identify omitted or inconsistent application → linked repair → reverify

2. Improve the codebase
   detect repeated or misplaced behavior → architecture proposal → review → bounded refactor

3. Improve how future work is performed
   compare repeated runs and outcomes → agent/procedure/context proposal → evaluation → activation
```

These loops may inform one another, but they never share automatic promotion authority. A repair
may not silently become a cross-stack refactor. A repeated implementation may not silently become a
Core abstraction. A successful run may not silently rewrite an agent definition, Pack policy,
framework, Context Manifest policy, routing rule, or verification gate.

## Why Code Intelligence is the first proof

Code is a dense, evaluable projection of the complete ACE operating loop:

```text
roadmap or user need
  → Decision and constraints
  → system impact
  → participant composition
  → implementation and handoffs
  → integrated verification
  → release
  → observed Outcome
  → governed improvement proposal
```

The proof remains broader than repository retrieval. ACE must connect why a change exists to the
symbols, services, schemas, tests, documentation, migrations, participants, authority, release,
and Outcome that realize it.

## Canonical inputs

Every improvement assessment resolves exact revisions of:

- Topic, objective, Decision, acceptance criteria, assumptions, and authorized scope;
- repository, branch, commit, worktree, package, service, deployment, and code-index identity;
- files, symbols, APIs, schemas, configuration, migrations, tests, documentation, and ownership;
- architecture decisions, public contracts, compatibility promises, security boundaries, and
  release requirements;
- Composition Plan, participant definitions, stage-role bindings, Context Manifests, tools,
  budgets, handoffs, run events, and results;
- changes, diffs, generated artifacts, verification evidence, review dispositions, and unresolved
  failures; and
- release, incident, adoption, reliability, performance, cost, correction, and other declared
  Outcome evidence.

An unavailable or stale input remains explicit. Code Intelligence never fabricates complete impact
coverage from a partial index, unobserved branch, unsupported language, missing source, or absent
verification route.

## Loop 1 — complete the current change

### Purpose

Determine whether an approved Decision was applied consistently across its declared and discovered
impact surface, then repair only the omitted or inconsistent portions inside the current change's
authority ceiling.

### Detection families

Code Intelligence may detect:

- an interface, API, schema, event, configuration, or policy change not propagated to every known
  implementation or consumer;
- tests, fixtures, SDKs, clients, examples, migrations, operational checks, or documentation that
  still encode the previous contract;
- a concurrent participant whose Context Manifest became stale after a dependency changed;
- duplicate or conflicting implementations created by parallel work;
- a reachable path that bypasses a new validation, authorization, error, observability, or recovery
  requirement;
- an acceptance criterion without corresponding verification evidence;
- a change that passes local tests but contradicts the governing Decision, Pack boundary,
  architecture rule, or public compatibility promise; and
- a partial, degraded, cancelled, or failed participant result represented incorrectly as complete.

### Repair contract

An `IncompleteChangeFinding` identifies:

- governing Topic and Decision revision;
- changed and expected impact surfaces;
- exact evidence supporting the omission or inconsistency;
- proven, derived, heuristic, unavailable, and intentionally excluded coverage;
- affected participant, context, dependency, contract, or acceptance criterion;
- consequence, urgency, and whether existing authority permits repair; and
- recommended linked repair or explicit exception.

A `LinkedRepairPlan` is a child of the original change and retains its own participant, manifest,
budget, tool, authority, verification, failure, and settlement receipts. It may repair only the
bounded finding. Expanding scope requires replanning and any additional authority.

### Completion gate

The loop completes only when:

- every finding is repaired, rejected with evidence, accepted as an explicit exception, or remains
  visibly unresolved;
- affected participants are revalidated against the current dependency and context heads;
- required tests, checks, reviews, migrations, documentation, and compatibility evidence pass or
  remain explicitly degraded;
- the integrated result is checked against the original Decision and acceptance criteria; and
- no repair modifies active cognition, Pack policy, agent definitions, permissions, or authority.

## Loop 2 — improve the codebase

### Purpose

Turn a local observation into a separately reviewed architecture opportunity when evidence suggests
that behavior should be reused, centralized, split, retired, or moved to a more appropriate layer.

### Candidate families

- repeated behavior that may deserve one reusable module or capability;
- one module that has accumulated unrelated policy and should be split;
- divergent implementations of one declared contract;
- a recurring adapter, validation, transaction, recovery, context, authority, or receipt pattern;
- functionality placed in a domain Pack, adapter, host, UI, or legacy arm that belongs behind a
  stable Core or Intelligence contract—or the reverse;
- a public or internal abstraction whose callers repeatedly bypass it;
- a compatibility shim that may be eligible for retirement; and
- an improvement that should propagate across packages, repositories, services, products, or the
  connected Product, Design, Data, and Operations graph.

### Evidence standard

Syntactic similarity is insufficient. An `ArchitectureOpportunity` must disclose:

- exact repeated or misplaced implementations and their owners;
- semantic behavior that appears common;
- differences that may represent distinct policy rather than parameters;
- current and proposed dependency direction;
- proposed ownership layer and why it satisfies ACE's constitutional boundary;
- compatibility, migration, security, performance, reliability, and organizational consequences;
- affected tests, consumers, adapters, Packs, tools, documentation, and release contracts;
- expected benefit and the evidence that makes it worth the blast radius;
- alternatives, including intentional duplication and no change; and
- rollback, verification, and Outcome measures.

### Architecture-proposal contract

An architecture opportunity creates no repair and no active module. An authorized reviewer may:

- reject it as false similarity, premature abstraction, incorrect ownership, or insufficient
  benefit;
- request investigation or a bounded prototype;
- accept intentional duplication with a review condition;
- approve a separately scoped refactor Decision; or
- defer it until additional repetitions, failures, or Outcome evidence exist.

An approved refactor receives a new Composition Plan and authority. It does not inherit the
original implementation change's grant merely because that change exposed the opportunity.

## Loop 3 — improve how future work is performed

### Purpose

Use repeated corrections, verification failures, participant outcomes, cost, latency, and later
product evidence to propose better agent definitions, context policies, decomposition, routing,
frameworks, review roles, procedures, and verification gates.

### Candidate families

- a class of change repeatedly omits the same dependency or acceptance evidence;
- a specialist participant materially improves migrations, security, accessibility, data,
  documentation, compatibility, or another bounded stage;
- a participant or stage repeatedly adds cost without material contribution;
- context is repeatedly missing, excessive, stale, or unused;
- parallel decomposition creates avoidable collisions or a sequential dependency is unnecessarily
  serialized;
- a verification check repeatedly catches the same preventable defect;
- a repair procedure succeeds often enough to be proposed as a governed reusable procedure; and
- a correction to ACE's own architecture or development process should influence later ACE work.

### Improvement-proposal contract

An `ExperienceImprovementProposal` identifies:

- exact completed runs, participants, manifests, corrections, failures, and Outcomes;
- the current agent, procedure, context, routing, framework, Pack-policy, or verification revision;
- proposed semantic diff and eligible scope;
- expected effect, cost, risks, expiry, conflicts, and rollback coordinates;
- matched-control or preregistered evaluation requirements;
- authority required to evaluate and activate it; and
- a supported no-learning result when evidence is insufficient.

The proposal-only background reviewer has no code-write, action, delivery, permission, memory-
promotion, policy-activation, or self-delegation authority. It may produce only bounded proposals
and an inspectable no-learning result.

### Promotion gate

A durable improvement may activate only after:

1. evidence quality and scope are reviewed;
2. the candidate revision is frozen;
3. matched evaluation compares it with the current revision on compatible tasks;
4. quality, coverage, Outcome, latency, cost, failures, and degraded states are reported;
5. the required human or deterministic authority approves the exact revision and scope;
6. prior revisions and rollback remain available; and
7. a later fresh run proves material use and measured effect without rewriting earlier history.

## Authority separation

| Transition | Default authority |
|---|---|
| Detect an incomplete application | Read and derive only |
| Propose a linked repair | Proposal only |
| Execute a repair | Exact bounded code/workspace authority plus ordinary participant manifest |
| Mark an exception intentional | Named Decision or review authority |
| Detect a modularization opportunity | Read and derive only |
| Approve a refactor | New architecture Decision and separately scoped action authority |
| Propose an agent or procedure change | Proposal only |
| Run a matched evaluation | Bounded evaluation authority with frozen candidates and fixtures |
| Activate an improved definition or policy | Explicit promotion authority for the exact revision and scope |
| Roll back or retire a revision | Separate lifecycle authority |

Installation, model output, code similarity, test success, majority preference, repeated use,
participant consensus, or the fact that ACE is operating on its own repository never grants any of
these authorities.

## Concurrent work and invalidation

Code Intelligence must continuously reconcile the current Decision, impact graph, participant
work, and repository heads while a change is active.

When one participant changes a dependency used by another, ACE records:

- the exact change event and dependency relation;
- affected participant runs and Context Manifests;
- whether the effect is proven, derived, heuristic, or unknown;
- applicable policy for notify, continue, pause, steer, cancel, or replan;
- the user's or controller's disposition; and
- the new plan, manifest, result, or explicit accepted risk.

Advisory ownership, scoped leases, overlap warnings, and integration checkpoints may coordinate
work. Git remains authoritative for commits, branches, diffs, and merges. The IDE or coding agent
remains authoritative for its local editing session. ACE owns the decision, impact, participant,
context, dependency, handoff, integration, and Outcome lineage surrounding that work.

## Atrium experience

Atrium exposes three distinct Attention types inside a Code Intelligence Topic:

### Incomplete change

Shows the governing Decision, covered and missing surfaces, stale participants, verification gaps,
and the evidence behind each finding. Permitted actions are inspect, expand impact, assign repair,
record an intentional exception, reverify, or leave unresolved.

### Architecture opportunity

Shows repeated implementations, semantic similarities and differences, current and proposed
ownership, blast radius, alternatives, benefit hypothesis, and required review. Permitted actions
are investigate, prototype, reject, defer, accept intentional duplication, or open a new refactor
Decision.

### Agent or procedure improvement

Shows supporting runs and Outcomes, current and proposed revisions, semantic diff, expected effect,
evaluation design, scope, conflicts, expiry, and rollback. Permitted actions are run evaluation,
approve, narrow, reject, defer, activate, roll back, or retire according to authority.

Atrium may summarize the evidence, but each state resolves to canonical objects and receipts. It
must never present one generic “Improve” action that hides which lifecycle and authority apply.

## ACE Builds ACE acceptance program

ACE is the reference Code Intelligence customer. The `ACE Builds ACE` program uses real bounded
roadmap work rather than synthetic editing exercises:

1. select and freeze one nontrivial ACE roadmap Decision with cross-cutting code, contract, test,
   documentation, migration, security, or release implications;
2. create a private Code Intelligence Topic over the exact repository and roadmap revisions;
3. run an honest coding-agent-only baseline and the same agent through ACE with equivalent model,
   tools, task, and authority;
4. have at least two human or agent participants perform concurrent work under separate Context
   Manifests;
5. introduce or observe one dependency change that makes another participant's context stale;
6. detect at least one true propagation gap or prove an explicit complete-coverage result;
7. complete a linked repair and integrated reverification without automatic scope expansion;
8. identify one architecture opportunity or produce an evidence-backed no-opportunity result;
9. complete review, merge, release-evidence, restart, and later Outcome linkage;
10. use repeated eligible experience to create one agent, procedure, context, routing, or
    verification proposal—or a justified no-learning result;
11. evaluate and govern any candidate revision separately; and
12. prove that neither repository access nor self-application granted ACE permission to approve,
    merge, release, promote, or widen its own authority.

The program reports orientation time, supplied and loaded context, evidence coverage, unsupported
claims, propagation recall and precision, overlap findings, stale-context detection, acceptance-
criterion coverage, review findings, repair count, rework, test and verification results, latency,
tokens, cost, failures, degraded states, release Outcome, and later material use.

One successful task does not establish self-improvement. The program must retain negative and
insufficient-evidence results and compare later governed revisions against frozen controls.

## Roadmap fit

### 1.1 — Code Intelligence

Productizes change-impact coverage, concurrent work reconciliation, stale-context and overlap
detection, integrated verification, propagation-gap findings, architecture opportunities, bounded
coding-agent handoffs, and the `ACE Builds ACE` reference program.

### 1.2 — Personal Intelligence

Lets an individual combine authorized project notes, files, decisions, and repository context
without turning personal-source access into repository-write or coding-agent authority.

### 1.3 — Intelligence Operations and Safe Evolution

Provides the canonical run event spine, participant lifecycle, verification, linked repair,
evaluation, restart, cancellation, settlement, and revision-safe upgrade substrate.

### 1.4 — Intelligence Pack Kit and Topic Intelligence

Makes a Code Intelligence Topic the governed workspace for Decision, impact, participants,
Attention, work, integration, Outcome, and improvement proposals. Packs contribute code-specific
lenses and policies without moving code semantics into Core.

### 1.5 — Organizational and Connected Product Intelligence

Extends propagation and reusable-architecture analysis across Product, Design, Code, Data,
documentation, operations, teams, repositories, and systems while preserving each pack and team's
ownership and permissions.

### 1.6 — Governed Self-Improving Agents

Adds proposal-only experience review, agent/procedure/context/routing/framework/verification
revisions, matched evaluation, explicit promotion, later material-use evidence, rollback, and
retirement.

### 1.7 — Portable Deployment and Interoperability

Runs the same loop across supported external coding agents, IDEs, repositories, and deployment
profiles without transferring canonical memory or authority to any participant.

### 2.0.0 — Collaborative Organizational Intelligence

Generalizes concurrent coherence and governed improvement from software delivery to multi-team,
multi-domain Decision Operations while Code Intelligence remains the most rigorously verified
reference projection.

## Deliberate non-goals

- unrestricted autonomous repository modification;
- automatic merge, release, deployment, or promotion;
- refactoring based on similarity alone;
- treating every duplication as an abstraction defect;
- treating a passing test suite as proof that the governing Decision was fully realized;
- converting one successful repair into a reusable procedure;
- allowing ACE to approve changes to itself;
- replacing Git, GitHub, an IDE, a coding agent, CI, or a deployment system;
- exposing hidden chain-of-thought; and
- claiming beneficial self-improvement without matched Outcome evidence.

## Decision test

Every Code Intelligence improvement capability must answer:

> Is this finishing the approved change, proposing a separate improvement to the codebase, or
> proposing an improvement to future work—and does its evidence, authority, evaluation, and
> rollback match that exact lifecycle?

If the answer is ambiguous, ACE must stop at an inspectable proposal or explicit uncertainty.
