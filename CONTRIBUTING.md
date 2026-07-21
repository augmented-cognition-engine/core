# Contributing to ACE

ACE is an open-source reasoning kernel — the engine that powers partner-team reasoning across any
domain. The 0.1.x contribution path covers the kernel, CLI/thin MCP contract, evaluation, docs, and
extension ecosystem. Atrium is a separately gated experimental visual-product/research track.

**Before you start, please read:**
- [`ROADMAP.md`](ROADMAP.md) — the public priorities and longer-term direction
- [`docs/capability-maturity.md`](docs/capability-maturity.md) — which surfaces are supported, experimental, conditional, dormant, or planned
- [`docs/architecture.md`](docs/architecture.md) — how the system works today
- [`docs/build-your-first-extension.md`](docs/build-your-first-extension.md) — the contributor entry point if you're building an extension

---

## Setup

Prerequisites are Git, Python 3.12, `uv`, and Docker Engine with Compose v2. SurrealDB listens on
**8001**, not its upstream default port. Atrium's experimental visual-product/research track has a
separate Node.js toolchain and is not part of preview setup. The ACE kernel is Apache-2.0; the
separately run SurrealDB server is
source-available under BSL 1.1 rather than OSI open source.

For the guided product-style path, run `uv sync && uv run ace setup`. The
expanded commands below remain useful for contributors who want each service
and migration step under explicit control.

```bash
# Backend (Python 3.12)
git clone <your-clone-url>              # e.g. your fork of this repository
cd ace                                  # the cloned directory
cp .env.example .env                    # set JWT_SECRET, API_KEY, and one real provider
docker compose -f infra/docker-compose.yml up -d surrealdb
uv sync                                 # installs Python deps
uv run python scripts/schema_apply.py
uv run uvicorn core.engine.api.main:app --host 127.0.0.1 --port 3000

# In another terminal
uv run ace login --api-key '<API_KEY from .env>'
uv run ace doctor
uv run ace model-policy
uv run python scripts/verify_golden_path.py

```

See the [README](README.md) quickstart for the authoritative end-to-end setup.

MCP and CLI are the developer-preview interaction paths. Atrium—the experimental
visual-product/research track—is present as a repository beta, not a supported Python artifact or
prerequisite for contributing to the engine.

---

## How to contribute

### 1. Find or open an issue

- Bugs: include reproduction steps, expected vs actual behavior, and the relevant subsystem (classifier / composer / deep committee / canvas / sentinel / foresight).
- Features: open a discussion first if the change touches an architectural contract from [`docs/architecture.md`](docs/architecture.md).

### 2. Pick the right surface

| You want to... | Touch this |
|---|---|
| Add a domain-specific recipe, persona, framework, or tool | An extension — see [`docs/build-your-first-extension.md`](docs/build-your-first-extension.md). Don't add it to the kernel. |
| Fix a kernel bug or improve a layer's behavior | `core/engine/{orchestrator,orchestration,cognition,capture,sentinel,foresight}/` |
| Add or evaluate an orchestration pattern | `core/engine/orchestration/` and `tests/orchestration/` |
| Add a MAKE or SHIP capability | `core/engine/arms/` with focused tests under `tests/` |
| Propose an Atrium HCI research change | Begin with the isolated research packet; do not expand the preview artifact |
| Improve evaluation and conformance | `tests/`, especially orchestration, intelligence, extension, and naked-kernel boundaries |

### 3. Run the tests

```bash
uv run pytest path/to/test_file.py -q       # focused check while iterating
make test-fast                          # pytest excluding e2e
ACE_DISABLE_EXTENSIONS=1 uv run pytest -m "not e2e and not requires_extensions" -q --tb=short
uv run ruff check <changed-python-files>
```

For extension changes, also run the extension's own test suite if it ships one (e.g. `uv run pytest extensions/<your-extension>/tests/ -m "not e2e"`); the reference extension (`extensions/reference/`) is covered by `tests/extensions/`.

Markers distinguish `e2e` and `requires_extensions` work from the default deterministic suite.
Do not make provider-quality claims from credential-free fixtures; follow
[`evaluations/README.md`](evaluations/README.md) for matched-model evidence and paid-live guards.

### 4. Conventions

**Commits:**
- Conventional commits format: `feat(area): summary` / `fix(area):` / `docs(area):` / `chore(area):` / `refactor(area):` / `test(area):`
- Body explains the *why*, not the *what* (the diff shows what)
- No AI co-author attribution — write what you wrote
- Never use `--no-verify` to skip hooks; fix the underlying issue

**Code:**
- Python: snake_case everything (modules, functions, files). Use `get_llm()` rather than raw provider imports.
- SurrealDB access uses `from core.engine.core.db import pool`, `async with pool.connection() as db`,
  `parse_rows(result)` for results, and `serialize_record(obj)` before JSON output. Add migrations
  under `core/schema/`, apply them with `uv run python scripts/schema_apply.py`, and test
  against namespace `ace_test`.
- TypeScript: no inline `color:` / `font-size:` / `padding:` — compose from `core/ui/canvas/src/design/components/`. New patterns extend the design system *first*, get used *second*.
- Tests live next to the code they cover. Extension tests in `<extension>/tests/`, kernel tests in `tests/`.

**Pull requests:**
- One concept per PR. Split big changes into atomic commits with tests green between them.
- Reference the issue (`Fixes #N`) if applicable
- Describe the *blast radius* — which subsystems, which tests, what could break
- Wait for CI green before requesting review
- Include focused and required conformance commands with exact results, documentation changes for
  public behavior, and evidence for maturity or performance claims. Link roadmap work to a public
  issue or Project item when one exists.
- Never include credentials, private graph exports, proprietary fixtures, or private-extension code.

The thin 11-tool MCP package and CLI are the preview contracts. The broad HTTP API, internal MCP
host, Atrium UI seams, and experimental extension hooks may change. Propose stable-contract changes
before implementation using [`docs/governance.md`](docs/governance.md).

### 5. Architectural contracts (don't break these)

These are described in [`docs/architecture.md`](docs/architecture.md). They are stable; changes to them require an explicit decision:

- **Provider Agnosticism** — no specific LLM provider in engine imports. Always `get_llm()`.
- **Surface Agnosticism** — engine emits events; surfaces subscribe. No UI imports in engine modules.
- **Modularity** — capabilities are recipe + instrument combinations addressable by slug.
- **Decision Lineage** — every meaningful choice gets a `graph_decision` row.
- **Forward Momentum** — every synthesis emits a forward-looking next move.
- **Nested Partnership** — `Human ↔ ACE ↔ LLM`. The LLM is computation, not loop controller.
- **Adaptive Framework Orchestration** — recipes select frameworks dynamically.
- **Mandatory Design System Use** — every UI component composes from `core/ui/canvas/src/design/components/`.

### 6. Extensions: the recommended contribution path

Don't copy `extensions/reference/` by hand — scaffold it:

```bash
python -m scripts.scaffold_extension <your_domain>
```

This copies the shipped reference extension and renames every identifier for
you (class, discipline, recipe, tool), so your starting point is a fully
wired, fully working extension, not a stub. From there:

1. Wire your recipes, instruments, personas, frameworks through the `Registry` facade.
2. Register via `ace.extensions` Python entry point (the scaffold wires this too).
3. Your extension package carries its own `tests/` — run them with `pytest` from your package. (Extensions living in-tree under `extensions/` are still picked up by the kernel's test discovery.)

The tutorial is canonical: [`docs/build-your-first-extension.md`](docs/build-your-first-extension.md) walks the full flow, file by file. Exact `Registry` contract: [`docs/extension-api.md`](docs/extension-api.md).

---

## Discussion

- **GitHub Issues** — bugs, feature requests
- **GitHub Discussions** — architecture questions, design discussions, "is this an extension or a kernel change?"
- **Security** — see [`SECURITY.md`](SECURITY.md). Do not file security issues in public GitHub Issues.

---

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0 (see [`LICENSE`](LICENSE)). You retain copyright to your contributions; you grant the project a perpetual license to use them under Apache-2.0.
