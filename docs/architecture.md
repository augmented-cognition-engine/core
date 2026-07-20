# ACE Architecture

**ACE — the Augmented Cognition Engine.** A reasoning core you partner with, not a chatbot you
operate. You bring a problem; ACE composes a problem-fit set of perspectives, routes them through
the model provider you configure, and synthesizes the result. The model does not drive the loop —
ACE does.

This document is the map: how the pieces fit, why they're shaped that way, and where your own work plugs in.

## Developer-preview as-built map (verified 2026-07-19)

This section records the repository that exists today. Statements labelled **verified** come from
source/import inspection or executable tests. Statements labelled **direction** describe the
boundary ACE intends to converge toward; they are not claims that every module already complies.

### Intended dependency direction

```mermaid
flowchart LR
    CONTRACTS[Kernel contracts\nSolution · LLMProvider · AgentShell · Extension]
    SERVICES[Kernel services\nclassification · composition · orchestration\ncapture · graph · learning]
    ARMS[MAKE / SHIP arms]
    ADAPTERS[Adapters and stores\nmodels · execution · SurrealDB]
    HOSTS[Runtime hosts\nHTTP API · CLI · worker · broad MCP]
    PUBLIC[Public thin MCP\n11 HTTP-backed tools]
    ATRIUM[Atrium\nexperimental API consumer]
    EXT[Extensions]

    CONTRACTS --> SERVICES --> ARMS
    CONTRACTS --> ADAPTERS
    SERVICES --> ADAPTERS
    HOSTS --> SERVICES
    PUBLIC --> HOSTS
    ATRIUM --> HOSTS
    EXT --> CONTRACTS
```

**Direction:** contracts and use-case services must not depend on a transport host. Hosts compose
services and adapters. Extensions depend on the registry/contract facade; core never imports an
extension package. The thin public MCP server is a remote HTTP adapter and never imports the
engine. Atrium consumes API and event state and is not a kernel composition root.

### Boundary and composition-root inventory

| Boundary / root | As built | Protection and status |
|---|---|---|
| Public MCP | `ace_mcp_client/server.py` registers exactly 11 wire tools; `client.py` and `tools.py` call the HTTP API | **Verified:** exact-name/count tests plus source and clean-process import guards; no engine or extension import |
| Full engine MCP | `core/engine/mcp/server.py` declares 112 built-in tools and eagerly adds extension tools at import through `registered_tools()` | **Verified:** broad advanced/experimental host; import-time extension discovery means it is not the preview contract |
| HTTP API | `core/engine/api/main.py` owns the FastAPI app, lifespan, database/schema startup, event/sentinel/notification registration, and a broad router list | **Verified:** largest composition root; required preview endpoints and legacy/experimental routes share one host |
| CLI | `core/engine/cli/main.py` imports and registers Click commands explicitly; commands primarily call HTTP | **Verified:** preview host, but broader than the minimal golden commands |
| Worker | `core/engine/worker/app.py` owns a separate FastAPI lifecycle, SurrealDB live query, capture processing, filesystem watcher, and session services | **Verified:** optional automation/runtime host; not required by the preview allowlist |
| Brain | `orchestrator/`, `orchestration/`, and `cognition/` implement classification, dispatch, patterns, composition, engagement, synthesis, and run traces | **Verified:** `orchestration/executor.py` is the principal reasoning use-case coordinator |
| Meta-Intelligence | `capture/`, `graph/`, `intelligence/`, `learning/`, `foresight/`, and `sentinel/` load and write durable intelligence, outcomes, predictions, and background signals | **Verified:** many modules access the shared DB pool directly; store boundaries are mixed with service logic |
| MAKE / SHIP | `arms/base.py` defines the abstract arm contract; code/design/data/scaffold are MAKE implementations and `ship_arm.py` is the composite gate | **Verified:** arm discovery is lazy but registration is decorator/import based in `arms/registry.py` |
| Model providers | `core/llm.py` owns `LLMProvider`, provider resolution, and several concrete routes; LiteLLM and any-llm adapters are optional extras and lazy imports | **Verified:** protocol is narrow; the main module still combines contract, resolver, and concrete Anthropic/subprocess implementations |
| Execution adapters | `runtime/adapters/`, `session/adapters/`, arm execution modules, Git/GitHub and command tooling connect approved intent to tools | **Verified:** multiple seams exist; there is not yet one preview-stable execution-adapter contract |
| Extensions | `extensions/base.py` defines `Extension`; `extensions/registry.py` is the facade; `loader.py` discovers `ace.extensions` entry points and `ACE_EXTENSIONS` | **Verified:** individual failures are logged and skipped; `ACE_DISABLE_EXTENSIONS=1` supports a naked kernel; the in-tree `extensions/reference` package is registered by `pyproject.toml` |
| SurrealDB/schema | `core/db.py` owns the pool; `core/schema.py`, `scripts/schema_apply.py`, and the versioned `core/schema/v*.surql` files own core migration order | **Verified:** graph/capture/intelligence services frequently query through the concrete global pool; extension schema registration exists but is documented as not consumed by the kernel migration runner |
| Atrium | `core/ui/canvas` is a separate React/Vite client using HTTP, WebSocket, and canvas/event APIs | **Verified:** it depends outward on host state and can fail independently of the MCP/CLI golden path |

### Durable public-task lifecycle

The public `ace_task` path is an asynchronous application boundary rather than a long-held model
request:

```text
thin MCP / CLI
→ authenticated POST /tasks
→ persist product- and user-owned receipt (pending)
→ bounded 202 response
→ in-process orchestration (running)
→ update the same task record with result, reasoning trace, and provenance
→ ace_status / GET /tasks/{id} retrieves terminal state and output
```

The receipt is created before provider or orchestration work, so losing the submitting connection
does not erase task identity or cancel execution. Retry identity is product/user scoped. The
single-process preview reconciles receipts left `pending` or `running` by a runtime restart to
`degraded`; it does not claim resumable distributed execution or public cancellation. Pattern
deadlines (normally 600 seconds), agent/provider deadlines, database acquisition/connect bounds,
and the thin client's ordinary 30-second HTTP timeout remain independent. Because submission no
longer waits for orchestration, MCP-host or proxy request limits do not set the reasoning duration.
Public semantic model aliases are resolved before orchestration, and receipt provenance falls back
to the selected provider and resolved request model when nested execution does not populate the
aggregate provider/model counters.

### Actual inward dependencies and duplication

The following are audit findings, not a request for a speculative rewrite:

- **Verified:** several MAKE/SHIP planners and strategy modules import functions from
  `core.engine.mcp.tools`. This reverses the intended direction: an arm depends on a host-oriented
  tool facade instead of a kernel service. It is deferred until M2 or a MAKE/SHIP path exercises a
  specific call, when that call can be moved behind an existing service with a compatibility shim.
- **Verified:** `foresight/forecaster.py` and `foresight/reconciler.py` import an API canvas helper,
  and `review/providers.py` imports an API PR helper. These are host dependencies inside services.
  They are outside the current preview signature path and need event/port extraction before G2 or
  execution hardening, not a directory move.
- **Verified:** the same eleven conceptual operations exist in both the HTTP-backed thin client
  and the broad in-process MCP server. Their transport behavior and return shapes differ, so the
  thin server is intentionally not implemented by importing the broad server. Contract-name drift
  is protected; shared generated descriptors are deferred until they have a second real consumer.
- **Verified:** the API lifespan and router registration are centralized and extensive, while
  sentinel and arm registration also relies on imports/decorators. This makes startup composition
  understandable only by reading roots and conventions. Extension and arm loading are isolated
  and idempotent, but full API registration remains broad.
- **Verified:** direct global-pool queries are widespread across graph, capture, and intelligence.
  `CaptureService` accepts a pool, but no uniform decision/run/intelligence store boundary exists.
  Introduce a store only when G1 or an exercised preview caller needs an independently testable
  read model; do not wrap every query pre-emptively.

### Optional and experimental seams

- Optional provider routers (`litellm`, `any-llm`), Discord, and browser tooling are dependency
  extras or guarded imports. Extensions have a process-lifetime kill switch and fail independently.
- Atrium, worker automation, sentinels, MAKE/SHIP execution, foresight/calibration, and the broad
  engine MCP are implemented but are not required by the developer-preview shipping allowlist.
- The API still mounts broad reporting, research, voice, notification, and compatibility routes.
  Their presence is not a public compatibility promise.

### Boundary evidence and remaining conventions

Executable tests protect core-not-importing-extensions, naked-kernel loading, reference registry
behavior, exact thin MCP names/count, thin source independence, and clean-process host isolation.
The intended no-host-imports-in-services rule, narrow store ownership, API profile composition,
and a unified execution-adapter boundary remain conventions with known exceptions. New violations
should not be added; existing exceptions should be removed only when an active scenario supplies a
real consumer and verification target.

---

## Inspired by the octopus

ACE takes architectural inspiration from the octopus: a lean coordinating brain working with
specialized arms. The analogy describes the intended distribution of coordination and specialized
work; it is not a literal claim about the ratio of code or intelligence in each component.

```mermaid
flowchart TB
    H([You]) <--> BRAIN

    subgraph BRAIN["🧠 The brain — the reasoning core"]
        direction LR
        CL[classify] --> CO[compose] --> EN[engage]
    end

    BRAIN --> MAKE
    BRAIN --> SHIP

    subgraph MAKE["🦑 MAKE arms — build"]
        direction TB
        M1[code]
        M2[design]
        M3[data]
    end

    subgraph SHIP["🦑 SHIP arms — gate what leaves"]
        direction TB
        S1[security]
        S2[testing]
        S3[observability]
        S4[devops]
        S5[scale]
    end

    MAKE --> SKIN
    SHIP --> SKIN
    SKIN([🎨 The skin — Atrium, the canvas you touch])
    SKIN <--> H
```

- **The brain** decides *who should think about this* and convenes them: `classify → compose → engage`. Selection combines explicit policy, configuration, and learned signals.
- **The arms** contain specialized MAKE and SHIP capabilities around the shared reasoning core.
  They are implemented for evaluation but remain experimental outside the stable 0.1.x contract.
- **The skin** is Atrium, the experimental ACE Canvas research track. MCP and CLI carry the
  supported developer-preview interaction path.
- **Extensions grow new arms.** A domain (personas, frameworks, recipes, instruments, tools, schema) attaches to the brain without forking it. That's the whole extension model, and it's covered in [build-your-first-extension.md](build-your-first-extension.md).

---

## The nested loop: `Human ↔ ACE ↔ LLM`

The single most important structural decision: **the LLM is inside ACE's loop, not the other way around.**

```mermaid
flowchart LR
    H([Human]) <-->|canvas / chat| ACE
    subgraph ACE["ACE — owns the loop"]
        direction TB
        ROUTE[routing] --- MEM[memory & graph] --- COMP[committee] --- FORE[foresight]
    end
    ACE -->|grounded prompt| LLM([LLM · Claude / GPT / Llama / local])
    LLM -->|reasoning only| ACE
```

The LLM is the inference resource ACE *calls* — it cannot write to the graph, choose the next
step, or decide which perspective speaks next. ACE owns those decisions. That separation keeps
the core provider-neutral across its documented routes and lets ACE shape model calls with retained
intelligence rather than surrendering orchestration to a provider.

ACE's Living Product Graph extends this ownership from reasoning into planning and execution. It
connects intent, outcomes, capabilities, decisions, work packets, dependencies, evidence,
observations, approvals, and learning. A roadmap is one projection of that graph—not a separate
task database—and Atrium is initially a view over the same kernel-owned state.

---

## The cognitive pipeline — 9 layers

The full architecture is organized as nine layers. The supported developer-preview path exercises
the reasoning, capture, graph, and retrieval loop; sentinel, foresight, calibration, and broader
automation remain experimental. **Layer 1, Meta-Intelligence** is the standing substrate of past
insights, decisions, capabilities, calibration, and sentinel state.

```mermaid
flowchart TB
    subgraph L1["① Meta-Intelligence — the standing substrate"]
        direction LR
        I[insights] ~~~ D[decisions] ~~~ C[capabilities] ~~~ CAL[calibration] ~~~ SEN[sentinel state]
    end

    L1 --> L2[② Classification — discipline, complexity, mode]
    L2 --> L3[③ Orchestration + Agent Composition]
    L3 --> L4[④ Engagement — the deep committee reasons]
    L4 --> L5[⑤ Disciplines × Frameworks]
    L5 --> L6[⑥ Synthesis — voices resolve to a recommendation]
    L6 --> L7[⑦ Decision + Graph Write]
    L7 --> L8[⑧ Sentinel — background engines watch for change]
    L8 --> L9[⑨ Foresight — predict, then reconcile at the deadline]
    L9 -.writes back.-> L1

    style L1 fill:#0d3b2e,stroke:#2fb48d,color:#e7ede9
```

The dotted line shows the design intent: exercised layers can feed accepted conclusions back into
Layer 1, so later work can load retained context. Persistence creates the opportunity for better-
informed later reasoning; it is not a guarantee that every run improves automatically.

---

## Dynamic composition — policy-guided and assembled at runtime

ACE does not use one fixed committee for every task. The classifier evaluates discipline,
complexity, and mode using explicit policy, configuration, and learned signals. The composer then
**assembles the reasoning shape at runtime** — which perspectives convene, which frameworks apply,
and how many phases the task receives.

```mermaid
flowchart LR
    T([a thought]) --> CLS[classify<br/>discipline · complexity · mode]
    CLS --> CMP{compose}
    CMP -->|picks WHO| WHO[perspectives<br/>e.g. PM · Skeptic · User-Advocate]
    CMP -->|picks HOW| HOW[frameworks & depth<br/>per perspective]
    WHO --> ENG[engage: parallel multi-voice,<br/>multi-phase deliberation]
    HOW --> ENG
    ENG --> SYN[synthesize<br/>voices → one grounded answer]
    SYN --> W[(write decision<br/>back to the graph)]
```

**Orchestration** picks *who* engages. **Composition** assembles *how* each one reasons. The path is
runtime-composed within explicit policies and compatibility boundaries; it is not an unconstrained
claim that every problem receives a perfect team. Extensions use the same public registration and
composition seams rather than a separate privileged path.

---

## Where your code plugs in

| You want to… | You touch… |
|---|---|
| Reason about a new domain | an **extension** — personas, frameworks, recipes, instruments, tools, schema, registered via the `ace.extensions` entry point |
| Add a reasoning capability | a **recipe + instrument** pair, addressable by slug; the composer routes to it by discipline, never by name |
| Contribute a pre-built team | a **committee** builder — a composed set of voices |
| Use a supported model route | configure one of the documented provider paths; the ACE loop remains separate from the provider |

Extensions never fork the core. They attach. The core ships empty of any single domain's specifics; you teach it yours. Start at **[build-your-first-extension.md](build-your-first-extension.md)**, and the stability you can build against is in **[extension-api.md](extension-api.md)**.

---

## Reading the code

| Layer | Lives in |
|---|---|
| Classification | `core/engine/orchestrator/` |
| Orchestration · composition | `core/engine/orchestration/` · `core/engine/cognition/composer.py` |
| Engagement (deep committee) | `core/engine/orchestration/deep_committee.py` |
| Meta-intelligence & graph | `core/engine/graph/` · `core/engine/capture/` |
| Sentinel engines | `core/engine/sentinel/` |
| Foresight | `core/engine/foresight/` |
| The canvas (skin) | `core/ui/canvas/` |
| The extension contract | `core/engine/extensions/` |

The brain coordinates; specialized components contribute depth around it. That is the design intent
behind the octopus metaphor.
