# Getting started with ACE

This is the supported ACE 1.0.3 installation and first-run path. It separates the stable package, full self-hosted runtime, provider-free contract evaluation, and contributor test gates.

## Quickstart

### Install the stable package

The distribution is `ace-core`; it provides the `ace` import package, the `ace` CLI, the packaged
Atrium workspace, and the `ace-mcp-client` command.

```bash
python -m pip install ace-core==1.0.3
python -c "import ace; print(ace.__version__)"
ace --help
```

The package includes Atrium, but Atrium is a view over the running ACE API rather than a second
source of truth. The supported full-stack path below uses a source checkout for the pinned Compose
stack and release-maintained service assets.

### Full self-hosted runtime

Running the reasoning service adds a database and a model provider.

**Prerequisites:** macOS or Linux · Git · Python 3.12 ·
[`uv`](https://docs.astral.sh/uv/) · Docker Engine with Compose v2 · credentials for one
[supported provider](https://github.com/augmented-cognition-engine/core/blob/main/docs/providers.md).

```bash
git clone https://github.com/augmented-cognition-engine/core ace
cd ace
uv sync
uv run ace setup
```

`ace setup` asks which model route to use, generates local credentials, writes `.env` with mode
`0600` without replacing existing secrets, starts SurrealDB through Docker Compose, applies every
migration, starts the ACE API as a local background process, and logs in the CLI and thin MCP
client. It is safe to rerun; if it is interrupted, run the same command again.

```bash
uv run ace doctor          # configuration, database, schema, auth, provider routing, API, MCP
uv run ace atrium          # open the personal Intelligence OS command center
uv run ace service status
uv run ace service logs --lines 80
uv run ace service stop    # preserves the SurrealDB volume
```

`ace doctor` verifies operational readiness only. It does not certify the correctness of data
already in the graph, and by default it spends no model tokens — add `--live-provider` for one
explicitly requested minimal call.

Manual control, for CI or development:

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d surrealdb
uv run python scripts/schema_apply.py
uv run uvicorn core.engine.api.main:app --host 127.0.0.1 --port 3000
uv run ace login --api-key '<the API_KEY from .env>'
```

### Evaluate the contract substrate — no database, provider, or keys

Core and Intelligence contracts are pure. From the checkout above, you can compile packs and
exercise the full derivation machinery without an external service:

```bash
uv run pytest tests/intelligence -q
```

That covers the Domain Pack compiler, detection, routing, synthesis, epistemic status, source
mapping, ledger, activation, and governed-reasoning suites.

### Test gates

```bash
make test-fast          # the fast suite (pytest -m "not e2e")
make test-naked-kernel  # the kernel with NO extensions loaded, plus the boundary guard
make lint               # ruff check + format --check
```

---
