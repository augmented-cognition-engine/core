# Local runtime operations

This guide covers the supported local ACE 1.0.3 topology: one ACE API/worker deployment and one
SurrealDB/SurrealKV database. It does not claim distributed ordering, multi-writer consistency,
multi-region failover, or exactly-once effects across independent databases.

## Managed service path

Guided setup creates private local credentials, starts the database and API, applies migrations,
and authenticates the CLI and thin MCP client:

```bash
uv run ace setup
```

Operate the resulting local service with:

```bash
uv run ace service start
uv run ace service status
uv run ace service logs --lines 80
uv run ace service stop
```

Stopping the managed service preserves the SurrealDB volume. Setup and service startup are safe to
rerun. Follow the exact recovery command printed by ACE before manually changing runtime or
database state.

## Readiness and provider checks

```bash
uv run ace doctor
```

The doctor verifies configuration, database reachability, schema, authentication, provider
routing, API readiness, and MCP registration. It does not certify the correctness of intelligence
already stored in the graph.

By default, it does not spend model tokens. Request one minimal live-provider call only when
needed:

```bash
uv run ace doctor --live-provider
```

See [Model providers](providers.md) for subscription-backed CLI routes, API keys,
OpenAI-compatible endpoints, local Ollama, billing semantics, and fallback controls.

## Manual development control

Contributors and CI environments may start each component explicitly:

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d surrealdb
uv run python scripts/schema_apply.py
uv run uvicorn core.engine.api.main:app --host 127.0.0.1 --port 3000
```

In another terminal:

```bash
uv run ace login --api-key '<the API_KEY from .env>'
uv run ace doctor
```

Never place credentials in documentation, fixtures, issues, shared logs, or copied terminal
transcripts.

## Choose the correct runbook

| Need | Guide |
|---|---|
| Install and reach first value | [Getting started](getting-started.md) |
| Configure a model route | [Model providers](providers.md) |
| Operate observation processing and leases | [Observation worker operations](worker-operations.md) |
| Perform State Engine ingestion, migration, backup, restore, or replay | [State Engine operations](state-engine-operations.md) |
| Reproduce the bounded State Engine product journey | [State Engine product builder](state-engine-product-builder.md) |
| Run a clean-user onboarding trial | [Onboarding trials](onboarding-trials.md) |

## Safety boundary

Domain Packs grant no network or execution authority. LIVE connectors and downstream adapters must
be explicitly registered, bound to exact artifact identity, and authorized for the exact source or
effect. Review [Trust, security, and governance boundaries](trust-and-security.md) before enabling
external I/O or consequential actions.
