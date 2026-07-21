# R1 effortless product onboarding evidence

Date: 2026-07-21  
Outcome: **passed**

R1 requires independent clean macOS and Linux journeys to reach a useful
reasoning result without maintainer help or ACE architecture knowledge. Both
journeys now pass. An initial Linux Ollama route reached readiness but failed
activation; the required clean Linux rerun used its own device-authorized Codex
credential, reached a useful result, and recovered from an intentional service
failure using product-facing guidance.

## Baseline and method

- PR [#8](https://github.com/augmented-cognition-engine/core/pull/8), “Add
  outcome-led guided onboarding,” was already merged as
  `7c6a20efd1f23d678291e329f3099bab8e4c5214` after six green checks and a
  safety review. It was not merged again.
- Merged-main CI was green before the trials:
  [run 29837568580](https://github.com/augmented-cognition-engine/core/actions/runs/29837568580).
- The trials began with the public README, PyPI page, and product-facing setup
  instructions. Internal architecture documentation was not used to rescue a
  journey.
- Each valid trial used a fresh clone, clean user configuration, fresh ACE
  bearer token, fresh `.env`, unique Docker project and volume, empty schema,
  and no maintainer ACE process or database.
- No independent human tester was available. These are AI-operated stranger
  trials in clean isolated environments, which are the best available proxy;
  they are not external human validation.
- Model responses and credentials were not copied into this report. Result
  quality is described only at the level needed to judge activation.

The synthetic builder intent was: build a B2B product, reason through whether
to launch a self-serve free trial or a guided paid pilot, preserve relevant
evidence, and produce a recommendation with success measures and revisit
criteria.

## Results at a glance

| Measure | macOS | Linux |
|---|---:|---:|
| Final outcome | pass | pass |
| Time from `ace setup` start to ready | 20.186 s | 25.496 s |
| Time from `ace setup` start to useful result | 104.432 s | 161.673 s |
| Full public journey through useful result | not instrumented | 242.762 s, including clone and dependency sync |
| Public-journey commands through activation | 3 | 5, including fresh device login and `ace setup --help` |
| Post-journey lifecycle/evidence commands | 5 | 6 |
| Provider configuration values | 1 route (`codex`) | 1 route (`codex`); no model value requested |
| Maintainer help required by final flow | no | no |
| ACE architecture knowledge required | no | no |
| Intentional recovery | Docker-engine recovery succeeded | actionable stop/start recovery succeeded after fix |
| `ace doctor` after restart | pass | pass |

The command counts exclude harness construction, prerequisite installation,
and environment-isolation variables. The macOS dependency sync took about ten
additional seconds; clone duration was not instrumented, so no unsupported
macOS end-to-end number is claimed. Linux's full-journey timer began immediately
before the public clone.

## macOS stranger trial

### Environment

- macOS 26.5 (build 25F71), arm64
- Python 3.12.7; uv 0.11.14
- Candidate revision `191fd70c56f31f4a1e65ef96b62a295fda6842f5`
- Codex CLI provider using an existing ChatGPT sign-in as an allowed model
  prerequisite; no ACE token, `.env`, provider configuration, database, or
  service was reused
- Colima Docker-compatible engine with a unique `ace_r1_macos_fixed` Compose
  project and a fresh schema migrated from 0 to 142

### Structured transcript

1. Read the product description and “Get your first recommendation” section.
2. Clone the candidate and run `uv sync`.
3. Run `ace setup` with the Codex route and the synthetic product decision.
4. Setup generated local secrets, verified the provider, started SurrealDB,
   applied schema 142, started the API, authenticated the CLI, and submitted a
   durable task.
5. ACE recommended a guided paid pilot first, with a bounded pilot cohort,
   duration, success metrics, evidence to retain, and conditions for revisiting
   the choice. This was a useful product-reasoning outcome.
6. `ace service status`, stop, start, `ace doctor`, and the onboarding report
   completed successfully. The preserved database volume reopened at schema
   142.

Warnings were limited to the Codex provider's explicit model-tier mapping and
subscription-capacity caveats. No credential appeared in terminal output or
the onboarding report. The final flow needed no undocumented command, ACE
architecture explanation, or maintainer intervention.

An intentional Docker-off attempt initially told a Colima user only to open
Docker. Recovery required knowing `colima start`; after that command the Docker
path recovered. The candidate now names both Docker Desktop and compatible
engines and gives `colima start` as the concrete Colima action. The recovery
text is covered by the focused setup tests.

## Linux stranger trial — passing rerun

### Environment

- Debian GNU/Linux 12 (bookworm), aarch64, in a fresh privileged
  Docker-in-Docker container
- Linux kernel 6.8.0-117-generic; Python 3.12.13; uv 0.11.30
- Docker 20.10.24; Docker Compose v5.3.1; Codex CLI 0.144.6
- Public merged-main revision
  `9c8d736d6862d9b4e42226e9e3705582f0557510`
- Codex CLI / ChatGPT subscription route, freshly authorized through the
  supported device-code flow inside the container; no host authentication,
  repository, `.env`, ACE state, provider configuration, SurrealDB state, or
  MCP configuration was copied or mounted
- Default capable route `gpt-5.6-terra`; fresh Compose project and schema
  migrated from 0 to 142

### Structured transcript

1. Enable the account's documented Codex device-code authorization setting,
   run `codex login --device-auth` inside the clean container, and complete the
   account consent flow. `codex login status` reported `Logged in using
   ChatGPT`.
2. Clone public `main`, run the README's `uv sync`, inspect public
   `ace setup --help`, and run `ace setup --provider codex` with this decision:
   whether a B2B workflow product for small operations teams should launch a
   five-partner paid pilot now or continue free discovery for six weeks.
3. Setup generated private local configuration, verified the provider, started
   SurrealDB, migrated schema 0 to 142, started the API, authenticated the CLI,
   and accepted durable task `task:5ylvzdwzr1rj5d8mvbpf`.
4. ACE recommended a tightly scoped paid pilot, conditional on a 48-hour
   evidence and qualification check. It supplied explicit assumptions, pilot
   scope and price, activation and outcome metrics, risks, a stop rule, and the
   next action. This directly answered the decision and was a useful result.
5. The onboarding report recorded one setup and activation success, readiness
   in 25.496 seconds, first result in 161.673 seconds, and no maintainer help or
   architecture knowledge. The timer from public clone through the result was
   242.762 seconds.
6. `ace doctor` passed configuration, schema 142, the Codex route, API,
   authentication, and 11/11 MCP tools.
7. An intentional `ace service stop` made database, schema, API, and
   authentication checks fail. The first doctor output lacked an actionable
   next command. The bounded fix now prints `ace service start`, its source
   checkout equivalent, `ace service logs --lines 80`, and the instruction to
   rerun doctor. Following that guidance preserved the database volume,
   restarted both services, and returned a fully green doctor result.

Warnings were limited to explicit provider-native model-tier sharing and the
fact that subscription capacity and latency depend on the provider plan. No
credential was printed or stored in the repository, and the journey did not
require ACE architecture, MCP internals, or repository knowledge beyond the
public source-checkout commands.

## Linux stranger trial — initial local-model attempt

### Environment

- Debian GNU/Linux 12 (bookworm), aarch64, in a privileged but otherwise clean
  Docker-in-Docker container
- Linux kernel 6.8.0-117-generic; Python 3.12.13; uv 0.11.30
- Docker 29.6.2; Docker Compose v5.3.1
- Candidate revision `191fd70c56f31f4a1e65ef96b62a295fda6842f5`
- Ollama reached over the harness-only host gateway; no host repository,
  `.env`, ACE auth, provider configuration, SurrealDB state, or MCP config was
  mounted
- Final route `qwen3:4b`; unique `ace_r1_linux_final` Compose project and a
  fresh schema migrated from 0 to 142

### Structured transcript

1. Read the public quickstart, clone the candidate from a bounded Git bundle,
   run `uv sync`, and inspect `ace setup --help`.
2. Run `ace setup --provider ollama` with the synthetic product decision.
3. Setup verified the model, started SurrealDB, applied schema 142, started the
   API, authenticated the CLI, and accepted durable task
   `task:6g59qaacwejxvwixdo18`.
4. The task remained `running`. Ollama completed several inference calls, but
   foresight JSON parsing warned twice and the durable task did not become
   terminal before the supported 900-second polling deadline.
5. Setup reported that the task might still be running and recommended
   `ace doctor` followed by a retry. The recorded activation rate was 0/1,
   readiness time was 19.049 seconds, and first-result timeout was 927.227
   seconds including setup work.
6. The initial `ace doctor` call found configuration, database, schema,
   provider, API, and MCP registration healthy but timed out on the protected
   authentication probe while the non-terminal task saturated the process.
7. Stop/start recovery restored a fully green `ace doctor`: configuration,
   schema 142, Ollama provider, API, authentication, and 11/11 MCP tools all
   passed.

A preliminary clean Linux run with `llama3.2:1b` returned after 162.476 seconds
but did not address the product decision usefully, so it was correctly rejected
as activation rather than counted as a pass. The provider also warned that all
semantic roles fell back to one local model because no model map was supplied.

The first Linux stop attempt exposed a false failure: the API had terminated,
but a zombie PID still answered `kill(pid, 0)`. The fix now verifies that the
PID is still ACE's managed Uvicorn command. The targeted rerun stopped the API,
stopped SurrealDB while preserving its volume, restarted both, and passed
`ace doctor`.

### Excluded harness attempts

- An Alpine/musl container could not install the declared `onnxruntime` wheel;
  Debian 12 was used for the faithful Linux trial.
- Installing all optional development extras filled a nested container with
  large accelerator packages. The container was discarded and the README's
  actual `uv sync` command succeeded in a fresh replacement.
- The first macOS attempt was contaminated by maintainer launchd services on
  ports 3000/8001 and was discarded before evidence was accepted.

These are harness mistakes or invalid trials, not product passes or failures.

## Friction found and bounded fixes

| Observed friction | Fix | Evidence |
|---|---|---|
| Active example Discord IDs crashed API startup with `ValueError` in both OS trials | Comment optional Discord settings in `.env.example`; ignore malformed optional IDs with a warning | macOS and Linux startup reruns reached ready; startup-config tests |
| API startup timeout did not name the supported log command | Point to `ace service logs --lines 80`, the log path, configuration repair, and rerun | focused setup test |
| Docker-off guidance assumed Docker Desktop | Name Docker-compatible engines and `colima start` | recovery test and recovered macOS attempt |
| Failed first activation still exited 0 and marked overall success | Preserve setup readiness, record activation failure, and exit nonzero with explicit incomplete-onboarding text | focused setup failure test |
| Linux zombie PID caused a false shutdown failure | Verify the PID still identifies managed Uvicorn during shutdown | focused lifecycle test and real stop/start rerun |
| `ace doctor` detected intentionally stopped services but gave no recovery command | Add prioritized text and JSON recovery actions for service, configuration, and provider failures | focused doctor test and clean Linux candidate rerun |

No credential handling was weakened, no data volume was deleted by service
stop, no public tool was added, and no Atrium, intelligence, extension, or broad
refactoring work was included.

## Verification

| Check | Result |
|---|---|
| Focused setup/startup tests | 25 passed |
| Final login/provider/doctor/setup plus roadmap/package matrix | 73 passed |
| Ruff lint and format | pass; 1,760 files formatted as-is |
| Fast non-E2E closeout | 6,267 passed, 46 skipped, 234 deselected in 111.93 s |
| Zero-extension non-E2E closeout | 6,259 passed, 47 skipped, 241 deselected in 114.18 s |
| Kernel boundary | 4 passed |
| Canvas | not changed; Canvas proxy checks passed in the fast suite |
| Packaging | wheel and sdist built; Twine passed both; R1 evidence present in the sdist and doctor recovery code present in the wheel |
| Docker | candidate image built; isolated Compose migration completed; API and SurrealDB healthy; `/health/live` and `/health/ready` returned `ok` with database, LLM, and pool checks healthy |

The closeout Compose health attempt initially failed with `No space left on
device` after the nested Linux trial occupied 4.04 GB. After the evidence was
captured, only that named disposable trial container (including its temporary
device credential) and the empty verification stack were removed. The identical
Compose migration and health command then passed.

PR [#10](https://github.com/augmented-cognition-engine/core/pull/10) merged the
initial trial fixes after its final six-check CI run
[29845492743](https://github.com/augmented-cognition-engine/core/actions/runs/29845492743)
passed Lint, Security Audit, Canvas, fast gate, naked kernel, and Docker Build.
Post-merge main run
[29845885052](https://github.com/augmented-cognition-engine/core/actions/runs/29845885052)
passed the same six jobs at
`9c8d736d6862d9b4e42226e9e3705582f0557510`. The passing Linux rerun and
doctor recovery change are in PR
[#11](https://github.com/augmented-cognition-engine/core/pull/11); its first
complete six-check candidate CI run
[29850236873](https://github.com/augmented-cognition-engine/core/actions/runs/29850236873)
passed Lint, Security Audit, Canvas, fast gate, naked kernel, and Docker Build.
Post-merge main is verified as an external closeout step because that run does
not exist until this evidence has merged.

The versioned roadmap files are reconciled to `passed`. The CLI token lacked
GitHub Project scopes, so the already-authorized GitHub browser session was used
without expanding persistent token privileges. The live public roadmap issue
now records R1 as `passed`, R2 as `ready`, the clean-trial measurements, the
AI-proxy limitation, and the durable evidence link.

## Remaining limitations and downstream state

- No independent human tester was available. Clean isolated AI-operated trials
  are the declared proxy and do not establish external human usability.
- Device-code login requires the account owner to enable the corresponding
  ChatGPT Security setting and approve the one-time account consent. This is
  standard authentication, not maintainer intervention, but it remains an
  explicit prerequisite for headless Codex routes.
- Subscription-backed latency and capacity vary by provider plan. The clean
  Linux setup-to-result measurement is evidence for this run, not a universal
  latency promise.
- The failed Ollama attempts show that operational readiness alone does not
  prove activation and that small local models may not satisfy the first-value
  outcome.

R1's product gate is complete. R2 may move to `ready`; no R2 implementation,
package publication, tag, or release is part of this closeout. R4 remains
dependency-blocked until R3 also passes.
