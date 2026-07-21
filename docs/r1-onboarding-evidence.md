# R1 effortless product onboarding evidence

Date: 2026-07-21  
Outcome: **ready — not passed**

R1 requires independent clean macOS and Linux journeys to reach a useful
reasoning result without maintainer help or ACE architecture knowledge. The
macOS journey passed. The Linux journey reached an authenticated, restartable,
`ace doctor`-ready installation but did not produce a useful result through the
credential-free Ollama route. R1 therefore remains `ready`.

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
| Final outcome | pass | fail at first useful result |
| Time from `ace setup` start to ready | 20.186 s | 19.049 s |
| Time from `ace setup` start to useful result | 104.432 s | not reached; timed out at 927.227 s |
| Public-journey commands through activation | 3 | 4, including `ace setup --help` |
| Post-journey lifecycle/evidence commands | 5 | 6 |
| Provider configuration values | 1 route (`codex`) | 2 (`ollama`, `qwen3:4b`) |
| Maintainer help required by final flow | no | no for setup/readiness; activation still failed |
| ACE architecture knowledge required | no | no |
| Intentional recovery | Docker-engine recovery succeeded | stop/start recovery succeeded after fix |
| `ace doctor` after restart | pass | pass |

The command counts exclude harness construction, prerequisite installation,
and environment-isolation variables. The macOS dependency sync took about ten
additional seconds; clone duration was not instrumented, so no unsupported
end-to-end number is claimed.

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

## Linux stranger trial

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

No credential handling was weakened, no data volume was deleted by service
stop, no public tool was added, and no Atrium, intelligence, extension, or broad
refactoring work was included.

## Verification

| Check | Result |
|---|---|
| Focused setup/startup tests | 25 passed |
| Login/provider/doctor/setup plus roadmap/package matrix | 189 passed, 3 skipped |
| Ruff lint and format | pass; 1,760 files formatted as-is |
| Fast non-E2E | 6,100 passed, 212 skipped, 234 deselected in 109.43 s |
| Zero-extension non-E2E | 6,092 passed, 213 skipped, 241 deselected in 116.62 s |
| Kernel boundary | 4 passed |
| Canvas | not changed; Canvas proxy checks passed in the fast suite |
| Packaging | wheel and sdist built; Twine passed both; corrected `.env.example` present in sdist and runtime fixes present in wheel |
| Docker | image built; isolated Compose migration completed; API and SurrealDB healthy; `/health/live` and `/health/ready` returned `ok` with database, LLM, and pool checks healthy |

The first Compose health attempt failed with `No space left on device` after
the nested Linux trials. Only the named disposable trial containers and empty
verification volume were removed; the identical health command then passed.

Candidate PR and post-merge main CI links will be added before closeout. The
pre-trial merged-main baseline is linked above.

The versioned roadmap files are reconciled to `ready`. The authenticated GitHub
CLI token lacks `read:project`, so the live Project could not be inspected or
updated. Expanding that token with persistent `read:project`/`project` scopes
requires separate explicit user approval; no alternate credential path was
used. The live evidence/blocker annotation therefore remains pending even
though no promotion to `passed` is being claimed.

## Remaining limitation and exact R1 blocker

Linux did not reach a useful product-reasoning result. A 1B local model returned
non-useful prose, and a 4B local model left the durable task running beyond the
900-second CLI polling deadline. A clean authenticated cloud/subscription route
was not available inside the isolated Linux environment without reusing a
maintainer credential, which the stranger protocol forbids.

Before R2 begins, rerun Linux in a fresh account/container with its own
authenticated supported provider (or a demonstrated local model/host capable of
finishing the same decision), require a useful completed result, rerun recovery
and `ace doctor`, append the evidence here, reconcile the live roadmap, and only
then move R1 to `passed`. R2 and R4 remain not ready.
