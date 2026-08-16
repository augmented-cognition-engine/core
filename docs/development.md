# ACE development guide

This compact repository map supplements [CONTRIBUTING.md](../CONTRIBUTING.md). Use [Getting started](getting-started.md) for installation, [Public Python API](python-api.md) for supported imports, and [Architecture](architecture.md) for system boundaries.

## Repository map

```
.
├── ace/                      ← the public package (this is the product surface)
│   ├── core/                 ← authority, immutable records, governed state, reasoning, decisions
│   ├── intelligence/
│   │   ├── contracts/        ← pack, resources, detection, synthesis, epistemic, ledger, monitors…
│   │   ├── packs/            ← compiler, runtime binding, activation, diagnostics
│   │   └── detection/        ← numeric delta, categorical transition
│   ├── application/          ← LIVE ingress, LIVE bridge, brief synthesis, decision feedback
│   └── testing/              ← packaged conformance seams for external packages
├── core/
│   ├── engine/               ← the host runtime (private): API, CLI, orchestration, adapters
│   ├── schema/               ← SurrealDB migrations (head: v177)
│   └── ui/canvas/            ← Atrium source for the packaged Intelligence OS workspace
├── ace_mcp_client/           ← thin pure-HTTP MCP client (the eleven tools)
├── extensions/reference/     ← the worked extension example the kernel actually loads
├── examples/                 ← independent example packages
├── docs/                     ← architecture, providers, maturity, operations, evidence
├── evaluations/              ← frozen fixtures and acceptance results
├── infra/                    ← docker-compose for SurrealDB + API
├── scripts/                  ← schema apply, journeys, verification, scaffolding
└── tests/                    ← including tests/intelligence, the no-service contract suite
```

`ace/` is the public boundary. `core/engine/` is the host and is private — public `ace` contracts
stay host-free, and host adapters are the only `core.engine` edge into the public package.

## Contributor setup

```bash
git clone <your-clone-url>
cd ace
uv sync
uv run ace setup --skip-first-task
```

Use [Local runtime operations](local-runtime.md) when you need explicit control over services,
migrations, logs, or recovery.

## Test gates

Run the smallest focused test while iterating, then the gates required by the affected boundary:

```bash
uv run pytest path/to/test_file.py -q
make test-fast
make test-naked-kernel
make lint
```

`make test-naked-kernel` disables extensions and proves that the public package and Core host do
not acquire an undeclared dependency on a domain extension. Product-quality, scale, or beneficial-
impact claims additionally require their frozen evaluation and evidence protocols.

## Contribution path

Read [CONTRIBUTING.md](../CONTRIBUTING.md) before changing stable contracts, schemas, authority,
pack semantics, or roadmap state. Domain vocabulary, policy, and integrations should normally enter
through a Domain Pack, Solution Bundle, connector, or documented extension boundary rather than a
Core branch.


---
