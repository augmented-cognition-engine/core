.PHONY: dev db-up db-down compose-up compose-down schema-apply ext-schema-apply test \
	test-fast test-naked-kernel test-e2e test-all test-canvas test-coverage \
	lint lint-fix audit health nightly weekly ci-fast ci-full \
	self-audit self-audit-report \
	spec-pre spec-post \
	eval eval-update-baseline eval-reasoning eval-reasoning-update-baseline

DOCKER_COMPOSE := $(shell docker compose version > /dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

# Development
dev: db-up
	uv run uvicorn core.engine.api.main:app --reload --port 3000

# Database
db-up:
	@if nc -z 127.0.0.1 8001 2>/dev/null; then \
		echo "SurrealDB already on :8001 (launchd, docker, or manual) — skipping startup"; \
	else \
		$(DOCKER_COMPOSE) -f infra/docker-compose.yml up -d surrealdb; \
		echo "Waiting for SurrealDB..."; \
		sleep 2; \
	fi

db-down:
	$(DOCKER_COMPOSE) -f infra/docker-compose.yml down

# Contributor / CI: one-command reproducible bring-up — SurrealDB 3.1.4 +
# schema (all core/schema/v*.surql) + API. Writes to a
# dedicated ./infra/data-dev store, never the real ./data/ace.db. See infra/README.md.
compose-up:
	$(DOCKER_COMPOSE) -f infra/docker-compose.yml up --build

compose-down:
	$(DOCKER_COMPOSE) -f infra/docker-compose.yml down

schema-apply: db-up
	uv run python scripts/schema_apply.py

# Apply an extension's schema: make ext-schema-apply EXT=<name>
# Runs every extensions/$(EXT)/scripts/apply_*_schema.py present. The kernel
# Makefile names no extension — extensions bring their own schema scripts.
EXT ?=
ext-schema-apply: db-up
	@if [ -z "$(EXT)" ]; then echo "Usage: make ext-schema-apply EXT=<extension-name>"; exit 2; fi
	@found=0; for f in extensions/$(EXT)/scripts/apply_*_schema.py; do \
		[ -f "$$f" ] || continue; found=1; \
		echo "→ $$f"; uv run python "$$f" || exit 1; \
	done; \
	if [ "$$found" = "0" ]; then echo "No apply_*_schema.py under extensions/$(EXT)/scripts/ — nothing to apply"; fi

# Testing
test: db-up
	uv run pytest tests/ -v

test-fast:
	uv run pytest -m "not e2e" -v
	uv run pytest tests/partnership/ -v

test-naked-kernel:
	ACE_DISABLE_EXTENSIONS=1 uv run pytest -m "not e2e and not requires_extensions" -q --tb=short
	uv run pytest tests/test_kernel_boundary.py -q

test-e2e: db-up schema-apply
	uv run pytest -m e2e -v

test-all: db-up schema-apply
	uv run pytest -v

test-canvas:
	cd core/ui/canvas && npx vitest run

test-coverage:
	uv run pytest -m "not e2e" --cov=core.engine --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"

# Eval — LLM-bound quality gate (NOT in ci-fast: costs tokens). Run before merges that
# touch routing/classification. Regresses only vs the committed baseline + tolerance.
eval: db-up
	uv run python scripts/eval_classifier.py

eval-update-baseline: db-up
	uv run python scripts/eval_classifier.py --update-baseline

# Reasoning-output eval — broadens the gate from classification to the full reasoning conclusion.
# LLM-bound (runs golden tasks through orchestrate); NOT in ci-fast. Same baseline-relative mechanism.
eval-reasoning: db-up
	uv run python scripts/eval_reasoning.py

eval-reasoning-update-baseline: db-up
	uv run python scripts/eval_reasoning.py --update-baseline

# Linting
lint:
	uv run ruff check .
	uv run ruff format --check .

lint-fix:
	uv run ruff check . --fix
	uv run ruff format .

# Security
audit:
	uv run pip-audit

# Health
health: db-up
	uv run python scripts/health_check.py

# Recurring
nightly: db-up schema-apply
	uv run pip-audit
	uv run pytest -v
	@echo "Nightly checks complete."

weekly: test-coverage
	uv pip list --outdated
	@echo "Weekly checks complete."

# Self-audit — run ACE on itself.
# Guarded: the tooling script ships with the private repo only; without it the
# target reports and succeeds rather than failing on a missing file.
self-audit: db-up schema-apply
	@if [ -f scripts/self_audit.py ]; then \
		uv run python scripts/self_audit.py --budget 50; \
		echo "Self-audit complete. Run 'make self-audit-report' to see results."; \
	else \
		echo "scripts/self_audit.py not present (private tooling) — skipping"; \
	fi

self-audit-report: db-up
	@if [ -f scripts/self_audit.py ]; then \
		uv run python scripts/self_audit.py --report-only; \
	else \
		echo "scripts/self_audit.py not present (private tooling) — skipping"; \
	fi

# Spec execution protocol — ACE-assisted pre/post loop (private tooling, guarded)
# Usage: make spec-pre SPEC=a2   (before implementing)
#        make spec-post SPEC=a2  (after implementing, before committing)
SPEC ?= ""
spec-pre: db-up
	@if [ -f scripts/spec_execute.py ]; then \
		uv run python scripts/spec_execute.py pre --spec $(SPEC); \
	else \
		echo "scripts/spec_execute.py not present (private tooling) — skipping"; \
	fi

spec-post: db-up
	@if [ -f scripts/spec_execute.py ]; then \
		uv run python scripts/spec_execute.py post --spec $(SPEC); \
	else \
		echo "scripts/spec_execute.py not present (private tooling) — skipping"; \
	fi

# CI
ci-fast: lint test-fast
	cd core/ui/canvas && npx tsc --noEmit && npx vitest run

ci-full: ci-fast test-e2e

voice-audit:
	@if [ -f scripts/voice_audit_ci.py ]; then \
		uv run python scripts/voice_audit_ci.py; \
	else \
		echo "scripts/voice_audit_ci.py not present (private tooling) — skipping"; \
	fi
.PHONY: voice-audit

as-built:
	@if [ -f scripts/generate_as_built.py ]; then \
		uv run python scripts/generate_as_built.py; \
	else \
		echo "scripts/generate_as_built.py not present (private tooling) — skipping"; \
	fi
.PHONY: as-built

as-built-check:
	@if [ ! -f scripts/generate_as_built.py ]; then \
		echo "scripts/generate_as_built.py not present (private tooling) — skipping as-built check"; \
	else \
		uv run python scripts/generate_as_built.py; \
		if ! git diff --quiet docs/ace-as-built.md; then \
			echo "❌ docs/ace-as-built.md is stale — run 'make as-built' and commit."; \
			git --no-pager diff docs/ace-as-built.md | head -40; \
			exit 1; \
		else \
			echo "✓ docs/ace-as-built.md matches current repo state."; \
		fi; \
	fi
.PHONY: as-built-check

# Fast pre-flight before pushing — courtesy check, not mandatory.
# Runs the same gates as pre-push hooks (typescript, pr-review, voice) but
# WITHOUT the heavy pytest run that lives on GitHub Actions CI now.
# Use this when you want a quick sanity check before `git push`.
push-check:
	@echo "→ typescript (canvas)"
	@bash -c 'eval "$$($$HOME/.local/share/fnm/fnm env --shell bash)"; cd core/ui/canvas && npx tsc --noEmit'
	@echo "→ canvas tests"
	@bash -c 'eval "$$($$HOME/.local/share/fnm/fnm env --shell bash)"; cd core/ui/canvas && npx vitest run'
	@echo "→ ACE PR review"
	@if [ -f scripts/pre_push_review.py ]; then \
		uv run python scripts/pre_push_review.py; \
	else \
		echo "scripts/pre_push_review.py not present (private tooling) — skipping"; \
	fi
	@echo "→ voice audit"
	@$(MAKE) voice-audit
	@echo "→ as-built manifest currency"
	@$(MAKE) as-built-check
	@echo "✓ pre-flight clean — safe to push"
.PHONY: push-check

# ── The canvas, as it actually ships ─────────────────────────────────────────
# Builds the canvas and serves it from the ACE canvas host: static files + the extension
# proxy seam (extensions/*/ui/canvas/canvas_proxy.json), forwarded SERVER-SIDE.
#
# This is the ONLY configuration that proves anything. `npm run dev` works because vite
# proxies the extension's data routes; a production build has no vite, so a canvas that has
# only ever been driven under `npm run dev` has never been driven at all.
canvas-build:
	cd core/ui/canvas && npx vite build

canvas-host: canvas-build
	uv run uvicorn core.engine.api.canvas_host:app --host 127.0.0.1 --port 5173

roadmap:  ## Regenerate ROADMAP.md from the spec database + docs/roadmap/areas.yml
	uv run python scripts/generate_roadmap.py

# Extension-local + workstation-local targets contributed by installed extensions.
# Absent from the export allow-list, so the leading `-` makes this a no-op in the
# public tree. Keeps the public Makefile extension-agnostic without breaking local.
-include Makefile.local.mk
