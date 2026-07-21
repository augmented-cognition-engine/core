# ACE public roadmap

This roadmap is the public view of work planned for ACE. It describes outcomes rather than
internal release operations, commercial plans, customer work, or security-sensitive details.
Priorities may change as maintainers learn from users and contributors.

## Current release checkpoint

`ace-core` 0.1.0 is published on PyPI and GitHub. The release, package artifacts, trusted
publishing path, and a clean public-index wheel installation have been verified. The current
onboarding gate is now proven in clean macOS and Linux proxy trials: a product builder can
understand ACE, reach a useful reasoning outcome, and complete the supported self-hosted
journey without maintainer knowledge or prior familiarity with ACE's architecture.

Roadmap outcome states are used strictly:

- **ready** — authorized and able to start;
- **active** — currently being executed;
- **candidate** — implementation exists, but evidence or reconciliation is incomplete;
- **not ready** — a dependency or acceptance gate remains;
- **passed** — outcome, verification evidence, limitations, and roadmap reconciliation are complete;
- **superseded** — replaced by an accepted newer outcome.

## Now — effortless product onboarding

- Publish and validate the `ace-core` 0.1.x Python distribution while preserving the `ace`
  import and CLI identities.
- Lead with the product outcomes ACE enables—better product context, reasoning, decisions,
  evidence, and learning—before introducing its architecture or developer surface.
- Make installation, authentication, provider setup, `ace doctor`, and the first useful journey
  guided and reliable for new users on macOS and Linux.
- Provide one obvious path from “what is ACE?” to a meaningful result, with progressive
  disclosure for the CLI, thin 11-tool MCP contract, self-hosting, and extension internals.
- Improve setup guidance, diagnostics, failure recovery, security reporting, and contributor
  onboarding from observed first-use friction.
- Protect the kernel/extension boundary and keep model-provider routes replaceable.

| ID | State | Public outcome | Dependency / acceptance evidence |
|---|---|---|---|
| R0 | passed | Publish `ace-core` 0.1.0 through a credential-free release path | GitHub Release, PyPI release, successful OIDC workflow, and public-index install verified |
| R1 | passed | Make first use effortless and outcome-led for product builders, not only developers | [Clean-trial evidence](docs/r1-onboarding-evidence.md): isolated macOS and Linux journeys both reached useful recommendations without maintainer help or architecture knowledge; intentional recovery and `ace doctor` passed |
| R2 | passed | Ship a focused 0.1.1 onboarding, packaging, and documentation release | [Release evidence](docs/r2-release-evidence.md): clean macOS/Linux installs, artifacts, required PR/main CI, `v0.1.1`, trusted PyPI publication, GitHub Release, and a fresh public-index install all passed against verified main commit `1662eaa` |
| R3 | candidate | Validate provider setup, authentication, diagnostics, and degraded behavior | Matrix, deterministic degraded-state coverage, one live GPT route, and green CI against current main are evidenced; an authorized live Claude route remains required |
| R4 | not ready | Publish a reproducible, product-builder golden-path demonstration | Depends on R1 and R3; must begin with a recognizable product decision and show capture, reasoning, durable restart, later material use, inspectable evidence, and honest limitations without requiring the audience to understand ACE internals |

## Next — durable product partnership

- Make product context, decisions, evidence, corrections, and outcomes easier to inspect.
- Improve evidence-bound reasoning, dissent, uncertainty, and human approval receipts.
- Strengthen long-running task recovery, replay, portability, and resource reporting.
- Turn Atrium research into a clearer read-only view of ACE state before adding new write or
  execution authority.
- Expand extension examples and conformance tests without widening the public MCP contract.

| ID | State | Public outcome | Dependency / acceptance evidence |
|---|---|---|---|
| G1 | candidate | Promote the read-only Living Product Graph projection into a supported inspectable journey | Kernel projection and boundary tests exist; public journey, failure behavior, compatibility boundary, and reproducible evidence remain |
| IA-R1 | not ready | Define the read-only information architecture for inspecting ACE state | Depends on G1 closeout; must preserve provenance, uncertainty, and object identity without adding write or execution authority |
| I1 | not ready | Make decisions, evidence, dissent, uncertainty, corrections, approval receipts, and outcomes easier to inspect | Depends on the developer-preview golden path and stable read contracts |
| T1 | not ready | Strengthen durable task recovery, replay, portability, cancellation semantics, and resource reporting | Requires explicit single-process versus distributed guarantees and failure evidence |
| E1 | not ready | Expand extension examples and conformance coverage | Must preserve the kernel boundary and exactly eleven public MCP tools |

## Later — build, ship, and learn

- Carry approved decisions through attributable implementation, review, repair, and promotion.
- Connect predicted outcomes to observed results so corrections can improve later reasoning.
- Support secure collaboration and managed operation without making the hosted service the
  owner of a user's durable intelligence.
- Grow a provider-neutral ecosystem of extensions and execution adapters.

| ID | State | Public outcome | Dependency / acceptance evidence |
|---|---|---|---|
| B1 | not ready | Carry approved decisions through attributable implementation, review, repair, and promotion | Requires I1 approval receipts and explicit execution authority |
| L1 | not ready | Connect predicted outcomes to observed results so corrections improve later reasoning | Requires stable outcome identity, provenance, and calibration evidence |
| H1 | not ready | Support secure collaboration and managed operation without transferring ownership of durable intelligence | Requires tenancy, portability, authority, and recovery guarantees |
| E2 | not ready | Grow the provider-neutral extension and execution-adapter ecosystem | Requires E1 conformance and stable compatibility policy |

## Follow and contribute

Follow the live [ACE Public Roadmap](https://github.com/orgs/augmented-cognition-engine/projects/1)
for current Now/Next/Later status. This file preserves the versioned outcome definitions and
public planning principles; repository issues carry discussion and acceptance evidence for
individual outcomes.

[`docs/roadmap-status.md`](docs/roadmap-status.md) records the latest reconciled evidence snapshot,
dependencies, and exact next dispatch. The GitHub Project is the live operational view; neither
strategy prose nor an unverified implementation claim advances an outcome to `passed`.

Public roadmap issues should state the user outcome, scope, acceptance evidence, dependencies,
and maturity impact. They must not contain credentials, vulnerability details, customer
information, private agreements, or unpublished business and release plans.
