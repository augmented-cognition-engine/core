# ACE frequently asked questions

This FAQ answers the operational questions that tend to appear after the architecture diagram:
what happens when part of a committee fails, how conflicting claims are handled, what confidence
means, and how multiple products share SurrealDB without becoming one undifferentiated memory.

ACE 0.1.x is a developer preview. Answers below distinguish the supported CLI and thin-MCP path
from broader engine capabilities whose APIs and end-to-end journeys remain experimental. See
[capability maturity](capability-maturity.md) for the authoritative boundary and
[architecture](architecture.md) for the as-built system map.

- [Mental model](#mental-model)
- [Partial failure and degraded operation](#partial-failure-and-degraded-operation)
- [Truth, conflict, confidence, and provenance](#truth-conflict-confidence-and-provenance)
- [Multiple products, tenants, and SurrealDB](#multiple-products-tenants-and-surrealdb)
- [Security, privacy, and operating boundaries](#security-privacy-and-operating-boundaries)

## Mental model

### Is the model the system?

No. ACE owns classification, context loading, composition, sequencing, synthesis, receipts, and
graph writes. The configured model supplies inference inside that loop. Provider-specific
capabilities still affect quality and tool access, but the model is not the orchestrator or system
of record.

### Is ACE just a chatbot with retrieval or a memory plugin?

No. Retrieval is one input to a larger cognitive loop. ACE retains typed nodes such as
observations, insights, decisions, work, predictions, and outcomes, plus typed relationships that
record dependency, provenance, conflict, and change. A final answer is therefore not the only
artifact of a run.

### Does every task convene a committee?

No. ACE dynamically selects an orchestration shape. A task may run independently or use a team,
pipeline, adversarial sequence, or parallel fan-out. The point is problem-fit composition, not
maximizing the number of model calls.

### Can I replace the model provider?

Yes. The core is provider-neutral and supports documented provider routes, including direct API,
subscription-backed CLI, OpenAI-compatible, and local Ollama configurations. Model availability,
tool use, latency, usage reporting, and billing semantics differ by route; see
[model providers](providers.md).

### Does ACE automatically improve after every run?

No. Accepted decisions, corrections, outcomes, and calibration signals can inform later work, but
persistence only creates the opportunity for better-informed reasoning. ACE does not treat every
generated answer as learning or promise monotonic improvement.

## Partial failure and degraded operation

### What happens when a tool call times out during a committee run?

The timeout should remain visible at the tool, agent, phase, or task boundary rather than being
rewritten as success. Tool runtimes use bounded calls where implemented, and orchestration retains
per-agent outcomes. What happens next depends on the selected shape: a team or fan-out can continue
when useful contributions survive, while a load-bearing independent or pipeline step may fail the
run.

ACE does not apply a blanket numeric confidence penalty for every timeout. Instead it preserves
the failed or missing contribution, the reduced coverage, and the resulting terminal state. The
durable public receipt's `execution` block reports contributor counts, statuses, bounded errors,
coverage ratio, tainted phases, and an attention marker when the result is partial.

### Does one failed committee member fail the whole task?

Not necessarily. Team and fan-out patterns can produce a result when at least one member succeeds;
their aggregate result records the total and successful contributor counts. If all members fail,
or if a failed step is required by a sequential plan, the pattern fails. A partial contributor
failure does not automatically mean the public receipt is `degraded` when the selected pattern can
still complete honestly; it can be `completed` with `execution.state="partial"` so usable output and
reduced coverage are both explicit.

### What do `pending`, `running`, `completed`, `failed`, and `degraded` mean?

- `pending` and `running` are non-terminal receipt states.
- `completed` means the selected orchestration produced a usable result.
- `failed` means execution did not produce a usable result.
- `degraded` means execution ended without a normal completion but retained an honest, retrievable
  receipt, such as after an upstream timeout or runtime interruption.

A client polling timeout is not itself a task failure. The reasoning job and its durable receipt
have a lifecycle separate from the client connection.

### What happens if the client, proxy, or MCP call times out?

Public tasks are submitted asynchronously. ACE persists the task receipt before long-running
orchestration and returns a task ID within a bounded submission window. The caller can retrieve the
same task later with `ace_status`; closing the original connection does not erase task identity or
imply cancellation.

### What happens if the ACE process restarts during a task?

The single-process 0.1.x runtime does not claim transparent resumption. On restart, receipts left
`pending` or `running` by the previous runtime are reconciled to `degraded`. Completed output remains
retrievable. Submit a deliberate retry with a new idempotency key when re-execution is required.

### Will retrying the same request duplicate work?

ACE reuses active identical work and same-hour automatic retries. A caller can also provide the
same explicit idempotency key to retrieve or repeat the same request identity. A new key signals an
intentional rerun. Retry identity is scoped to the product and user.

### Does ACE fail open or fail closed?

It is a scoped decision, not one global policy:

- Optional context and background intelligence generally fail open, with missing or degraded
  context made observable where the path supports it.
- Invalid graph writes and cross-product isolation violations fail closed.
- Conflicting claims fail closed for promotion into operational truth, while unrelated work can
  continue.
- A load-bearing execution failure fails or degrades the task rather than fabricating completion.

### Is every write transactional?

No. The atomic capture path writes an insight, its provenance edges, and its embedding state in one
SurrealDB transaction, so a statement failure aborts that unit. Missing embeddings use an explicit
`needs_embedding` state for later reconciliation. Broader orchestration and background workflows
span multiple steps and should not be described as one database transaction.

## Truth, conflict, confidence, and provenance

### What happens when two arms write conflicting facts?

ACE does not use last-write-wins for relational truth. Arms create provenance-bearing proposal
events. The assertion resolver rebuilds canonical state from persisted proposals using stable
identity and deterministic, order-independent policy. Mutually exclusive assertions in the same
scope become `contested` and are excluded from the operational projection of the Living Product
Graph.

The disagreement remains inspectable; it is not deleted merely because it cannot yet drive an
operational decision.

### Does ACE bring conflicts to the user's attention?

Yes on the implemented conflict path. The detector atomically persists a product-scoped `pending`
conflict and quarantines both insight claims as `contested`, so ordinary active-intelligence
retrieval cannot silently use either. It also writes a durable attention signal. The conflict API
returns both claims, confidence, provenance, quarantine state, allowed resolution actions, and the
resolution endpoint; portal attention and briefings can surface the same conflict.

The important maturity boundary is that automatic, immediate delivery of every conflict through
every external notification channel is not a stable 0.1.x guarantee. Conflict persistence,
quarantine, and durable attention are the load-bearing behavior; Sentinel scheduling,
notifications, and broad graph UI/API journeys remain experimental.

### Does confidence matter?

Yes, but confidence is evidence about a claim, not authority to declare it true. ACE can retain
proposal confidence, evidence strength, provenance quality, freshness, reviewer confidence, and
calibration. These signals can influence review depth, ranking, uncertainty, and escalation.

They do not make model confidence a last-write-wins tie-breaker. Ontology validity, type
compatibility, evidence requirements, persisted objections, provenance, and required human
confirmation can all prevent a high-confidence proposal from becoming operational truth.

### Can ACE be confidently wrong?

Yes. Any inference system can. ACE's answer is inspectability and correction, not a claim of
infallibility: source records, assumptions, evidence, model/provider route, reviews, decisions, and
later outcomes can be retained so confidence can be checked against reality.

### Can two contradictory claims both remain in the graph?

Yes. The historical and epistemic graph may preserve both as contested assertions. Neither is
eligible for the operational projection until the conflict is resolved. Preserving disagreement
is safer and more auditable than deleting the losing claim prematurely.

### Does a conflict block the entire loop?

No. It blocks promotion of the contested claim and should gate decisions that materially depend on
it. Independent work can continue. Consequential or unresolved decisions can defer, escalate, or
request human resolution without freezing unrelated graph activity.

### Who can resolve a contested assertion?

The deterministic resolver can transition an assertion when the policy inputs change, and a human
can confirm consequential claims where required. Arbitrary agents cannot directly promote a
contested assertion to accepted operational truth.

### What happens when evidence is later corrected or invalidated?

Assertions grounded in changed evidence can be marked contested and removed from operational
projection. A bounded truth-maintenance walk marks dependent assertions stale, records the reason,
and rebuilds the projection. This focuses re-evaluation on affected beliefs rather than treating
the entire graph as invalid.

### Is model-generated content treated as external evidence?

No. Capture records origin and provenance, and ACE assigns lower trust priors to its own generated
reasoning and composition than to direct human capture. Generated material can become a proposal
or insight, but it is not silently laundered into independent evidence.

### What exactly does provenance contain?

The available fields depend on the artifact, but can include source records, evidence references,
origin type, product, user, surface, workflow, provider, model, prompt or policy version,
timestamps, trust, and the task receipt. Provenance makes a claim inspectable; it does not by
itself prove that the source was correct.

### Is Sentinel the authority that decides truth?

No. Sentinel watches for gaps, drift, changes, contradictions, and emerging evidence. It records
correlated runs and findings and can initiate focused review. Canonical assertion status is governed
by the assertion resolver and human-confirmation policy, not by an unconstrained background model.

## Multiple products, tenants, and SurrealDB

### Can one ACE deployment store multiple products in the same SurrealDB instance?

Yes. Product-scoped records carry a canonical `product:<id>` reference, and a tenant can own
multiple products. Product, task, intelligence, decision, capability, project, signal, and other
engagement queries are expected to scope by that product reference. Portfolio APIs can
intentionally aggregate products within the same tenant.

The default deployment uses one SurrealDB namespace and database rather than creating a separate
database for every product.

### Why does ACE use SurrealDB?

ACE needs durable records and typed graph relationships in the same substrate. SurrealDB supports
record links, graph traversal, ordinary indexed queries, full-text search, and vector indexes
without reducing the product's memory to an embedding collection. The graph is the system of
record; embeddings are retrieval aids.

The choice does not remove the need for schema migrations, query scoping, backups, or application
validation. ACE pins and documents the supported SurrealDB path rather than assuming every server
version has identical behavior.

### What is the difference between a tenant, product, project, and ecosystem?

- A **tenant** is the ownership boundary that can contain multiple products.
- A **product** is the primary reasoning and retained-intelligence scope carried in authentication
  and graph records.
- A **project** can link a repository or delivery context to a product.
- An **ecosystem** expresses an intentional relationship among products or projects for portfolio
  views and selected cross-product behavior.

The product is the key isolation unit for ordinary task and memory retrieval.

### How does a user switch products?

The broad HTTP host can reissue a JWT scoped to a target product after verifying that the current
and target products belong to the same tenant. Task ownership checks compare the authenticated
product with the task record and return not-found behavior for mismatches. These portfolio and
product-switching APIs are implemented but outside the narrow 0.1.x CLI/thin-MCP compatibility
surface.

### Are product names or IDs tenant-local?

Not currently. Product creation derives a canonical `product:<slug>` record ID and rejects an
existing ID across the shared database. Operators should therefore choose deployment-wide unique
product slugs. Tenant-qualified product IDs would be a future schema/API decision, not something
to assume in 0.1.x.

### Can one product accidentally retrieve another product's memory?

Product-scoped loaders and graph projections filter by the product reference. Runtime isolation
validators raise named errors when returned records or signals belong to another product, and the
Living Product Graph projection excludes cross-product records and relationships rather than
presenting them as local truth.

This is application-level isolation in a developer preview, not an independently certified
database row-security boundary. Deployments needing regulatory, contractual, or adversarial tenant
isolation should use separate ACE/SurrealDB deployments or another dedicated infrastructure
boundary until their own security review establishes otherwise.

### Is any knowledge intentionally shared across products?

Yes. Frameworks, skills, and other universal knowledge can be intentionally global. Selected
ecosystem workflows can copy high-confidence specialty insights to connected products, preserving
the source product in provenance. Cross-product portfolio views are also intentional.

Shared data should be explicit and provenance-bearing. Product-scoped engagement data should not
become shared merely because it lives in the same database.

### Does shared SurrealDB mean all products share one Living Product Graph?

They share a storage substrate, not one undifferentiated operational view. The Living Product Graph
service projects a deterministic snapshot for a requested `product:<id>`, excludes records outside
that scope, and reports projection issues. Intentional portfolio or ecosystem views are separate
cross-product queries.

### Are embeddings shared across products?

Embeddings live on product-scoped records, and retrieval queries are expected to apply the same
product boundary as lexical and graph retrieval. An embedding is not a separate source of truth or
permission boundary. If embedding generation is unavailable, atomic capture can retain the record
with `needs_embedding=true` so a reconciler can backfill it later.

### What happens to retained memory when I change model providers?

The graph remains in SurrealDB and is not owned by the model provider. Later runs can load retained
intelligence through a different configured provider. Existing receipts and proposals keep their
original model/provider provenance so a provider change does not rewrite history.

### What happens if a relationship points across products?

Ordinary product snapshots exclude cross-product records and relationships and surface an issue
instead of projecting them as operational truth. An intentional cross-product capability should
use an explicit portfolio or ecosystem contract with provenance, not an accidental unscoped edge.

### Can multiple products be processed concurrently?

Yes within the bounds of the host and database pool, and product identity is carried through task,
retrieval, and persistence paths. The supported preview runtime is still single-process: it does
not claim distributed task claiming, transparent resumption, or a general multi-writer distributed
consensus protocol.

### How are concurrent conflicting graph writes serialized?

Within one process, relational assertion persistence uses a critical section, stable event IDs,
idempotent writes, and replay of the persisted proposal set so arrival order does not determine
truth. Multi-process deployments must place that path behind one assertion writer until a
distributed compare-and-swap or equivalent coordination mechanism is implemented.

### Should I use one SurrealDB deployment or one per customer?

For local development, internal use, or a trusted team, one deployment can hold multiple products
with product and tenant scoping. For hard customer isolation, data residency, regulated workloads,
or independently administered tenants, prefer dedicated deployments. The correct boundary is a
security and operations decision, not merely a database-capacity decision.

### What should be backed up?

Back up the SurrealDB data volume and the deployment configuration required to reconnect ACE to its
provider and database. `ace service stop` preserves the managed SurrealDB volume; preservation is
not the same as a backup. Backup schedules, restore drills, retention, encryption, and off-site
copies remain operator responsibilities in the self-hosted preview.

### Can I delete or export a whole product through the stable public API?

Not as a stable 0.1.x compatibility contract. Product-scoped export helpers and broader management
APIs exist, but complete product portability and cascading deletion require an explicit, tested
operator journey. Until that is promoted, use deployment-level backups and carefully reviewed
administrative procedures rather than assuming that deleting one product record deletes every
related node and edge.

## Security, privacy, and operating boundaries

### Does self-hosted mean no data leaves my environment?

Not automatically. ACE and SurrealDB can run locally, but a remote model provider receives the
context sent for inference, and enabled external tools or notification channels may transmit data.
Use a local provider and disable external integrations when the requirement is fully local
processing.

### Does ACE store API keys in the graph?

Provider credentials are deployment configuration, not reasoning context. They should be supplied
through the documented environment or login path and must not be captured as observations or
inserted into prompts. Public task errors are bounded and redact common secret patterns, but that
does not replace normal secret-management practice.

### Are Sentinel and continuous-learning features always running?

No. They depend on the host, configuration, feature registration, schedules, and provider access.
Sentinel engines can run on registered schedules or explicit triggers. Their broad APIs and
end-to-end operating journeys remain experimental in 0.1.x.

### What is the stable public contract today?

The compatibility focus is the self-hosted CLI, exactly eleven thin MCP tools, the documented
provider routes, migrations, and reference extension boundary. The broad HTTP APIs, Atrium,
Sentinel scheduling, MAKE/SHIP execution, worker automation, foresight, calibration, and continuous
learning are implemented but not compatibility-stable 0.1.x contracts.

### What should operators test before trusting ACE with important work?

At minimum, rehearse provider and tool timeouts, partial committee failure, process restart,
idempotent retry, database unavailability, conflicting assertions, invalidated evidence,
cross-product access attempts, backup restoration, and the human-resolution path. Verify the
actual deployment and enabled host rather than inferring production guarantees from the
architecture alone.
