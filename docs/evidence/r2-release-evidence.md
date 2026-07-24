# R2 ace-core 0.1.1 release evidence

Date: 2026-07-21
Outcome: **passed**

R2 is the focused 0.1.1 onboarding, packaging, and documentation release. Local verification,
required PR and merged-main CI, the `v0.1.1` tag, trusted PyPI publication, GitHub Release, fresh
public-index installation, repository roadmaps, and the live Project item are reconciled and green.

## Exact release scope

- Lead the public entry with one outcome-led product-builder path: bring a real decision, choose
  a supported provider, run guided setup, and receive a recommendation.
- Make the PyPI description concise and outcome-led and make every root README documentation link
  absolute so it works outside a repository checkout.
- Align the distribution, `ace` import, thin MCP client, engine, reference extension, lockfile, and
  public support inventory at version 0.1.1.
- Make setup/provider/doctor recovery usable from an installed CLI by linking the public quickstart
  and provider guide and naming exact next commands.
- Correct top-level CLI identity to “Augmented Cognition Engine.” Hide the legacy experimental
  `ace skills` command and `ace run --skill` option from default help while preserving both exact
  compatibility paths.
- Default manual trusted publishing to `v0.1.1` and fail closed when the release tag and package
  metadata version differ.

The release does not widen the eleven-tool MCP contract, redesign Atrium, add intelligence or
learning behavior, rename legacy skills into a new abstraction, add commands or schemas, begin R3
or R4, or refactor cognition architecture.

## Changed public journey

The README now exposes the four-command source-checkout quickstart before architecture and
developer material. The package-only path is explicit about what the wheel supplies and why the
pinned self-hosted Compose stack still uses a checkout. `ace setup --help` names all supported
provider choices and distinguishes API keys, subscription-backed routes, local Ollama, and
existing configuration. Missing runtime assets point directly to the public quickstart. Provider
diagnostics point to the absolute provider guide. `ace doctor` continues to return prioritized
service, configuration, authentication, and provider recovery actions.

Default `ace --help` now identifies ACE correctly and does not promote the legacy `skills`
surface. Default `ace run --help` does not promote `--skill`. `ace skills --help` and
`ace run --skill <slug> ...` remain accepted and retain their existing behavior.

## Clean installed-artifact checks

Both checks installed the locally built wheel with dependencies into a new environment. Neither
used the maintainer virtual environment, repository `.env`, ACE token, provider configuration,
database, running service, or MCP configuration.

| Environment | Isolation | Result |
|---|---|---|
| macOS 26.5 (25F71), arm64, Python 3.12.13 | New `/private/tmp/ace-r2-clean-macos-wheel/venv`; fresh `ACE_CONFIG_DIR`; commands run outside the checkout under `env -i` | pass |
| Debian GNU/Linux 12 bookworm, aarch64, Python 3.12.13 | New `python:3.12-slim-bookworm` container; only the wheel copied in; fresh `/tmp/ace-config`; no host state mounted | pass |

Each environment verified:

- distribution, `ace`, and thin-client version 0.1.1;
- import success and packaged schema 142, onboarding copy, and default model-policy resource;
- exactly eleven thin MCP tools;
- corrected top-level identity and callable CLI;
- understandable provider choices in `ace setup --help`;
- absence of `skills` and `--skill` from default help;
- continued `ace skills --help` callability;
- missing-runtime recovery links the public quickstart and exact checkout command;
- clean `ace doctor --json-output` failure returns actionable setup recovery.

The Linux verification container had no volumes and was removed after evidence capture. The
macOS environment contains no credentials or local ACE state.

## Package and archive inspection

Commands:

```text
uv build --wheel --sdist
twine check dist/*
unzip -p dist/ace_core-0.1.1-py3-none-any.whl ace_core-0.1.1.dist-info/METADATA
unzip -l dist/ace_core-0.1.1-py3-none-any.whl
tar -tzf dist/ace_core-0.1.1.tar.gz
```

Results:

- built `ace_core-0.1.1-py3-none-any.whl` and `ace_core-0.1.1.tar.gz`;
- Twine passed both archives and the long description rendered as Markdown;
- wheel and sdist metadata agree on name `ace-core`, version 0.1.1, Python 3.12, Apache-2.0,
  concise summary, and public project URLs;
- the wheel contains schema migrations through v142, onboarding JSON, runtime model policy,
  recipe/report templates, thin MCP client, reference extension, license/notice, README,
  changelog, roadmap, and public docs including R1 evidence;
- the sdist contains build inputs, package sources, scripts, evaluations, public docs, license,
  notice, and the same runtime resources;
- neither archive contains `.env`, credentials, Git data, caches, ACE config, API PID/log files,
  databases, SQLite files, Atrium source, or test state; `.env.example` remains an intentional
  placeholder-only sdist input;
- all root README non-anchor links are absolute HTTPS links, enforced by a package regression test.

No additional installed-resource fix was necessary: clean wheel installs exposed all resources
used by the supported installed checks. The complete self-hosted local-service journey remains
honestly documented as a source-checkout path rather than silently downloading runtime assets.

## Verification results

| Check | Result |
|---|---|
| Focused CLI identity, legacy compatibility, onboarding, setup, login, provider, doctor, lifecycle, package, build-backend, and roadmap matrix | 230 passed, 3 skipped |
| Ruff lint | pass |
| Ruff formatting | 1,760 files already formatted |
| Fast non-E2E suite | 6,274 passed, 46 skipped, 234 deselected in 139.47 s |
| Zero-extension non-E2E suite | 6,266 passed, 47 skipped, 241 deselected in 132.24 s |
| Kernel boundary | 4 passed |
| Security audit | no known vulnerabilities; local unpublished `ace-core==0.1.1` correctly skipped as unavailable on PyPI |
| Canvas | not affected; no Canvas file changed; full Canvas gate remains required in PR CI |
| Wheel and sdist | built and inspected |
| Twine | both archives passed |
| Clean macOS wheel install | pass |
| Clean Linux wheel install | pass |
| Release workflow | Actionlint passed; matching `v0.1.1` accepted; mismatched `v0.1.0` rejected; nothing published |
| Docker image | no-cache build passed |
| Fresh Docker Compose stack | schema 0→142 validated; migration exited 0; SurrealDB and API healthy |
| Docker HTTP checks | `/health/live` and `/health/ready` returned `ok`; ready version was 0.1.1 |

## Warnings, failures, and reruns

- A focused startup test could not bind a loopback port inside the filesystem sandbox. The same
  module passed 4/4 with local socket access; this was an environment restriction.
- The first macOS resource probe imported a runtime package whose normal configuration validation
  requires `JWT_SECRET`. Resource inspection was corrected to use installed distribution metadata;
  the package resource was present and no product change was needed.
- Colima did not expose the host `/private/tmp` or `/tmp` paths as bind mounts. The wheel was copied
  into a clean named container instead; the full Linux check passed.
- An API-only image probe exited with the documented error because no SurrealDB was present. The
  required fresh Compose stack then migrated successfully and passed both health endpoints.
- Docker reported that the classic builder is deprecated and Buildx is not installed. Builds
  succeeded; this is host-tooling maintenance, not an R2 product failure.
- Pytest emitted existing FastAPI/Starlette/websockets deprecations, test-only JWT key-length
  warnings, collection warnings for model classes named `TestCase`/`TestSuite`, and two
  unawaited-mock runtime warnings. No warning was introduced by or blocks R2.
- Trusted publishing emitted GitHub's Node.js 20 deprecation warnings for the pinned v4 artifact
  actions, which GitHub ran on Node.js 24; both build and publish jobs passed.
- The first public-index install attempt immediately after trusted publishing saw only 0.1.0.
  After normal index propagation, the same cache-free 0.1.1 install succeeded.

All disposable Linux and Compose containers, the verification network, and the fresh disposable
database volume were removed after capture. No maintainer service, database, provider route, or
credential was touched.

## Public release gates and URLs

Completed public gates:

- ready release PR: https://github.com/augmented-cognition-engine/core/pull/12;
- final candidate CI: https://github.com/augmented-cognition-engine/core/actions/runs/29854879422
  (`success`; all six jobs green in 4m32s against
  `8f9698691d16f442c922cfaaf607c69449d1f6d7`);
- verified merged-main commit: https://github.com/augmented-cognition-engine/core/commit/1662eaa9b31b88e80de95966906afab59e7c2505;
- merged-main CI: https://github.com/augmented-cognition-engine/core/actions/runs/29855304378
  (`success`; all six jobs green in 4m37s);
- tag: https://github.com/augmented-cognition-engine/core/tree/v0.1.1 (resolves to the verified
  merged-main commit);
- trusted-publishing run: https://github.com/augmented-cognition-engine/core/actions/runs/29855826494
  (`success`; distributions built, attested, and published in 52s);
- GitHub Release: https://github.com/augmented-cognition-engine/core/releases/tag/v0.1.1;
- PyPI: https://pypi.org/project/ace-core/0.1.1/;
- fresh Python 3.12 public-index install: `pip install --index-url https://pypi.org/simple
  --no-cache-dir ace-core==0.1.1` passed, then confirmed distribution 0.1.1, corrected CLI
  identity, hidden-but-callable legacy compatibility surfaces, and exactly eleven thin MCP tools;
- live roadmap item: https://github.com/augmented-cognition-engine/core/issues/1 records
  `R2 — passed` with the public evidence links.

The release commit descends from verified R1 merge
`ba73a3daae5a6bc5e61fd55446af5cfe14cceff5`. R3 may proceed independently. R4 remains blocked
until R3 passes as well.

## Remaining limitations

- Python 3.12 is the only supported interpreter.
- The full self-hosted journey uses a source checkout for pinned Compose and local service assets.
- R1 usability evidence is an AI-operated clean proxy, not independent human validation.
- Provider result quality, capacity, billing, and latency depend on the selected provider and plan.
- Legacy `skills` CLI/API/code remains callable compatibility surface; R2 changes visibility only
  and does not begin recipe convergence or migration.

R2 is complete. Exact next work is R3 provider, authentication, diagnostics, and degraded-state
validation. R4 remains dependency-closed until R3 also passes.
