# ACE product vision

ACE is the **Augmented Cognition Engine**: an open, provider-neutral system for turning changing
context into accountable decisions, coordinated work, and measurable outcomes.

Its commercial category is **Decision Operations**. Its technical form is a **governed cognitive
runtime**. Neither description is sufficient alone: ACE must improve how a person or organization
understands, reasons, decides, coordinates people and agents, acts through existing tools, and
learns from what actually happened.

> **ACE does not generate everything. It keeps everything working from the same decision.**

The product must be immediately useful to one person and become more valuable as participation
grows. It must not require an enterprise rollout to help an individual, and it must not turn into a
collection of disconnected personal assistants when used by a large organization.

> **Single-player useful. Multiplayer compounding.**

## The problem ACE owns

AI has made generation abundant. It has not solved continuity of judgment.

People and organizations still reconstruct context from documents, conversations, dashboards,
repositories, tickets, and prior model sessions. Decisions become detached from their evidence and
reasons. Specialized tools receive inconsistent direction. Agent work becomes difficult to inspect,
resume, govern, or compare. Outcomes rarely return to improve the next decision.

ACE owns that missing operating loop:

```text
observe → understand → reason → decide → coordinate → act → verify → learn
```

Models, agents, applications, and domain tools participate inside or downstream of the loop. ACE
owns the durable state, context assembly, participant composition, authority, decision lineage,
handoffs, outcomes, and receipts that make the loop coherent.

## What ACE is—and is not

ACE is:

- a living orientation over a bounded question, objective, system, or mission;
- a reasoning and decision environment grounded in attributable evidence;
- an orchestration control plane for people, models, agents, deterministic logic, and tools;
- an authority boundary that makes permissions, budgets, approvals, and effects explicit;
- a continuity layer connecting decisions to downstream work and later outcomes; and
- a governed improvement loop that proposes better memory, procedures, routing, frameworks, and
  agent definitions from verified experience.

ACE is not:

- a universal chatbot, prompt library, or chat-history store;
- a replacement for Figma, Codex, Canva, a CRM, a BI platform, an ERP, or another mature system of
  design, generation, transaction, or record;
- one omniscient company prompt or an undifferentiated global knowledge graph;
- an autonomous authority that can silently widen its own access, tools, budgets, or goals; or
- a claim that more agents, more participation, or more model confidence means a better result.

Specialized products remain the hands. ACE supplies the governed intelligence that tells those
hands what matters, why, under whose authority, with which constraints, and how the result will be
evaluated.

## The experience promise

Every ACE experience should answer five questions before exposing infrastructure:

1. **What changed?**
2. **Why does it matter here?**
3. **What decision or work needs attention?**
4. **Who or what is doing it, under which limits?**
5. **What happened, and what should be remembered?**

Topics are the primary user-facing unit of that experience. A Topic is a governed runtime workspace
for a question, objective, watch, investigation, or decision. It composes only the authorized
evidence, intelligence, memory, frameworks, participants, capabilities, budgets, and delivery
policy needed for that bounded purpose.

Atrium makes the loop legible. Its default path is bottom line → connections → evidence and
reasoning → decision → active work → outcome. Infrastructure views remain available for people who
need to inspect sources, Packs, manifests, authority, run events, failures, and receipts.

## One architecture from one person to 10,000

The scale invariant is:

> **Cardinality changes. Semantics do not.**

The same Topic, Evidence, Observation, Decision, Action, Outcome, Participant, Run, Context
Manifest, Capability Grant, and Receipt contracts must work when their governed scope contains one
principal, a small team, a department, an enterprise, or a federation of organizations.

A one-person deployment is a fully governed workspace of one, not a toy or a special local schema.
The initial principal may simultaneously be owner, operator, decision-maker, and approver. ACE
creates safe defaults for those roles while still recording the scope and authority that made an
operation valid.

As participation grows, those roles separate. ACE adds principals, groups, scopes, delegated
authority, approval thresholds, privacy boundaries, organizational relationships, recovery, and
managed-operation controls without replacing the underlying objects or migrating intelligence into
a second product.

The promotion path must be continuous:

```text
personal workspace
    + invited participants
    + shared Topics and explicit roles
    + organization overlays and policy
    + federated scopes and operations
= the same durable intelligence, with more boundaries and coordination
```

Adding the second user or the ten-thousandth must not invalidate existing identity, provenance,
decisions, memory, links, or receipts.

### Progressive disclosure

Complexity is revealed only when it helps the current user:

- an individual starts from a Topic, connects a few sources, and receives an orientation;
- a team sees ownership, handoffs, disagreement, decisions, and shared outcomes;
- an administrator sees identity, policy, tenancy, data boundaries, health, and audit; and
- an advanced builder sees Packs, adapters, participant definitions, manifests, conformance, and
  lifecycle controls.

The individual does not need to understand the infrastructure required to keep the individual's
work portable and safe.

### Progressive governance

Governance scales with **consequence**, not merely headcount.

A private, reversible research step may require no interruption. A production deployment, customer
communication, financial transaction, policy change, or sensitive-data operation may require
review even when performed by one person. Conversely, low-risk investigation should not become
bureaucratic merely because it occurs inside a large organization.

Every action path therefore resolves risk, authority, reversibility, destination, budget, and
required review from the active scope and operation. Enterprise policy can narrow those rules; it
cannot turn installation, transport, model confidence, or participant selection into authority.

### Federated cognition

Organizational scale does not mean centralizing every fact or exposing every source.

- Authorization is evaluated before relevance.
- Derived intelligence is never less restricted than its inputs.
- Teams retain ownership of local vocabulary, evidence, decisions, and policy.
- Cross-scope relationships are explicit, attributable, and permission-aware.
- Topics compose bounded views rather than copying whole graphs into prompts.
- Dissent, minority views, uncertainty, and conflicts of interest remain first-class.
- Organization-to-organization operation uses federation or governed exchange, not assumed trust.

ACE should create shared cognition without erasing identity, permissions, disagreement, or
accountability.

## Value at each scale

### Individual developer: a project that does not forget

ACE maintains the connection among user needs, issues, architecture, code, tests, incidents,
dependencies, decisions, and outcomes. It can identify likely blast radius, assemble appropriate
coding and review participants, hand a bounded task to Codex or another coding tool, collect the
result and verification, and preserve whether the change achieved its intended outcome.

The coding tool generates or edits code. ACE preserves why the work exists, what constrains it,
who authorized it, what else it affects, and what was learned.

Code Intelligence also provides the first rigorous expression of governed self-improvement. After a
change, ACE distinguishes three questions:

1. **Was the approved change completed everywhere it applies?** Detect omitted consumers, stale
   tests, migrations, documentation, concurrent work, or acceptance evidence; then perform a linked
   `verify → repair → reverify` loop inside the existing authority ceiling.
2. **Did the change expose a reusable architecture opportunity?** Identify repeated or misplaced
   behavior, semantic differences, correct ownership, blast radius, alternatives, and expected
   benefit; then open a separate architecture Decision rather than silently refactoring.
3. **Should future humans and agents perform this kind of work differently?** Use repeated
   corrections, costs, failures, and Outcomes to propose a revised agent definition, context policy,
   decomposition, routing rule, framework, procedure, or verification gate; evaluate and promote it
   only through explicit governance.

ACE uses its own development as the reference proof. The **ACE Builds ACE** program connects a real
roadmap Decision to code impact, concurrent human and agent work, bounded coding-tool handoffs,
propagation checks, integrated verification, release evidence, later Outcome, and a governed
improvement proposal or justified no-learning result. ACE may diagnose, propose, coordinate, and
verify changes to itself; it may not approve, merge, release, promote, or widen its own authority.

### Independent business owner: operating memory and follow-through

ACE watches the authorized signals across customers, revenue, operations, commitments, and the
external environment. It produces a decision-oriented brief, frames options and risks, records the
owner's decision and reasons, coordinates bounded work through the owner's existing systems, and
returns to the observed outcome.

The owner spends less time reconstructing the business from tabs and conversations and more time
making and completing decisions with continuity.

### Researcher, analyst, or consultant: a living investigation

ACE preserves sources, competing explanations, assumptions, uncertainty, revisions, and decision
implications across a long-running question. Client, project, and private scopes remain separate.
New evidence updates the investigation without rewriting what was previously known or claimed.

### Small team: shared orientation without more meetings

ACE gives the team a common Topic, current bottom line, visible evidence, unresolved disagreement,
decision record, participant work, handoffs, and outcomes. New members can recover why the present
state exists without treating a summary or chat transcript as the source of truth.

### Enterprise: accountable coordination across boundaries

ACE connects external and internal change to affected products, systems, teams, policies,
decisions, and outcomes. Each participant receives only the authorized context and capabilities
needed for the current work. Leaders can inspect decision and outcome lineage without bypassing
the ownership or access boundaries of the teams that produced it.

Enterprise value comes from shared orientation, reduced duplicated investigation, safer agent
operation, faster cross-team handoff, preserved institutional reasoning, and measurable outcome
learning—not from creating a larger chatbot.

## The product architecture

ACE remains one product with clear internal responsibilities:

```text
Sources and systems of record
        ↓
Core + Intelligence runtime
  identity · evidence · graph · reasoning · authority · outcomes · receipts
        ↓
Topics
  bounded context · frameworks · participants · budgets · decisions · work
        ↓
People and governed agent composition
        ↓
Bounded handoffs to systems of action
  Figma · Codex · Canva · CRM · BI · ERP · domain tools
        ↓
Artifacts, effects, measures, and corrections return to ACE
        ↓
Governed memory and improvement proposals
```

Intelligence Packs contribute reusable meaning, policies, frameworks, detectors, views, and
evaluation fixtures. Organization Overlays specialize them without forking. Adapters connect
sources and destinations. External agents participate as scoped principals. Atrium exposes the
human control plane. None becomes a second state, memory, reasoning, or authority system.

## Product editions without product forks

Commercial packaging may progressively add managed capability while retaining one semantic
kernel:

| Product form | Primary value | Additional operating capability |
|---|---|---|
| ACE Core | Fully useful local intelligence and Decision Operations for one | Open contracts, self-hosting, provider choice, personal workspace |
| Managed Individual | Continuity with less operational work | Managed sync, backup, updates, and selected integrations |
| Team | Shared cognition and coordinated work | Shared Topics, roles, handoffs, team memory, evaluation, and outcome review |
| Enterprise | Governed organizational intelligence | Identity federation, policy, audit, data boundaries, reliability, recovery, federation, and support |

The quality of reasoning and ownership of portable intelligence must not be reserved for an
enterprise edition. Larger deployments pay for coordination, governance, integration, reliability,
and managed operation—not for access to the "real" cognitive engine.

## Measures of success

ACE should be evaluated on completed cognitive work, not response volume or agent activity.

For an individual:

- time required to become oriented in an existing Topic;
- repeated context that no longer needs to be supplied manually;
- proportion of material claims grounded in authorized evidence;
- decision-to-completed-outcome cycle time;
- avoided rework from remembered decisions, constraints, and corrections; and
- outcome, cost, latency, and failure differences against a matched non-ACE workflow.

For a team or organization:

- context lost at handoffs;
- duplicated investigation and conflicting uncoordinated work;
- time to recover decision rationale or onboard a participant;
- policy violations, denied operations, and unreceipted effects;
- cross-team decision-to-outcome cycle time;
- ability to preserve and resolve disagreement; and
- attributable improvement from later material use of governed experience.

Participation, token volume, number of agents, consensus, model confidence, and artifact delivery
are not substitutes for a beneficial outcome.

## Vision acceptance tests

ACE is advancing this vision only when it can prove all of the following:

1. A new individual can create one useful Topic and reach a grounded decision without configuring
   an organizational platform.
2. That individual can invite a collaborator without exporting, re-ingesting, or losing the Topic's
   identity, decisions, memory, provenance, or receipts.
3. A low-risk operation remains lightweight while a high-consequence operation requires the
   appropriate authority and review at any organization size.
4. Multiple teams can collaborate on one permission-sensitive Topic without receiving unauthorized
   source material or collapsing dissent into a false consensus.
5. An external agent or system of action receives only bounded context and authority, returns a
   typed result, and cannot become ACE's source of truth.
6. A completed outcome can create a reviewable improvement proposal, and a later matched run can
   establish whether the approved change helped.
7. The same contracts survive local, managed, dedicated, and federated deployment with explicit
   capability differences and no loss of user ownership.
8. Code Intelligence can distinguish an incomplete implementation, a separate reusable-architecture
   opportunity, and an agent or procedure improvement; each follows its own evidence, authority,
   evaluation, and rollback lifecycle.
9. ACE can use this loop on its own repository under an honest matched baseline without granting
   itself implicit approval, merge, release, deployment, or promotion authority.

The enduring product promise is:

> **One person gets a cognitive partner that can act responsibly. Ten thousand people get shared
> cognition without losing identity, permissions, disagreement, or accountability.**
