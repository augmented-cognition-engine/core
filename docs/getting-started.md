# Getting started with ACE

This is the supported ACE 1.2 installation and first-run path. It is checkout-free: everything a
first-time user needs ships in the published packages and the release artifacts. Contributor and
development paths follow at the end.

## Quickstart

### Install the stable package

The distribution is `ace-core`; it provides the `ace` import package, the `ace` CLI, the packaged
Atrium workspace, and the `ace-mcp-client` command.

```bash
python -m pip install ace-core==1.2.2
python -c "import ace; print(ace.__version__)"
ace --help
```

`ace --help` works before any configuration exists; nothing requires a `.env` until you start the
runtime.

### Personal Intelligence

Personal Intelligence ships as a Solution Bundle beside `ace-core`: the
`ace-personal-intelligence-pack` distribution (the domain pack and its onboarding profile), the
pure-data `ace-personal-intelligence-bundle` distribution (the exact bundle manifest), and the
read-only local-source adapter family. Install them from the artifacts attached to the matching
[GitHub Release](https://github.com/augmented-cognition-engine/core/releases):

```bash
python -m pip install \
  ace_personal_intelligence_pack-*.whl \
  ace_personal_intelligence_bundle-*.whl \
  ace_local_markdown_source-*.whl ace_local_pdf_source-*.whl \
  ace_local_csv_source-*.whl ace_local_json_source-*.whl \
  ace_local_source_normalizers-*.whl
```

The pack carries the Personal onboarding profile; installing it makes Personal Intelligence appear
in the catalog and lets `builds/prepare` plan the journey. All bundle sources are local and
read-only; nothing personal leaves your machine as a requirement of the bundle.

### Full self-hosted runtime

Running the reasoning service adds a database and a model provider.

**Prerequisites:** macOS or Linux · Python 3.12 · Docker Engine with Compose v2 · credentials for
one [supported provider](https://github.com/augmented-cognition-engine/core/blob/main/docs/providers.md).

```bash
ace setup
```

`ace setup` asks which model route to use, generates local credentials, writes its configuration
with mode `0600` without replacing existing secrets, installs the pinned Compose definition into
`~/.ace/runtime`, starts SurrealDB, applies every migration, starts the ACE API as a local
background process, and logs in the CLI and thin MCP client. It is safe to rerun; if it is
interrupted, run the same command again.

Setup is fail-closed about ownership: it never migrates a SurrealDB that already contains ACE
schema from another installation (pass `--adopt-existing-database` to adopt one deliberately), and
it never treats a foreign process answering on its port as the ACE API.

Isolation on a machine that already runs ACE — set these before `ace setup`:

```bash
export ACE_CONFIG_DIR=~/.ace-second       # configuration and runtime assets
export ACE_API_PORT=13000                 # API port (default 3000)
export ACE_SURREAL_HOST_PORT=18041        # SurrealDB host port
export COMPOSE_PROJECT_NAME=ace_second    # Docker Compose project and volume
```

```bash
ace doctor          # configuration, database, schema, auth, provider routing, API, MCP
ace atrium          # open the personal Intelligence OS command center
ace service status
ace service logs --lines 80
ace service stop    # preserves the SurrealDB volume
```

`ace doctor` verifies operational readiness only. It does not certify the correctness of data
already in the graph, and by default it spends no model tokens — add `--live-provider` for one
explicitly requested minimal call.

## Contributor and development paths

Manual control from a source checkout, for CI or development:

```bash
git clone https://github.com/augmented-cognition-engine/core ace
cd ace
uv sync
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
