# R3 provider, authentication, diagnostics, and degraded-state evidence

Evidence date: 2026-07-21

Repository base: `7c6a20e` (PR #8 merged)

R3 state: **candidate**

R3 is not passed. The supported matrix and deterministic degraded-state evidence are frozen, and
one authorized GPT route is live-validated. No authorized Claude API key, setup token, or CLI
session is available in the validation environment, so a real Claude smoke request and complete
branch CI remain the exact missing acceptance evidence. No credential value or model response is
stored in this report.

## Configuration and authentication precedence

Process environment values override `.env`; `.env` overrides `Settings` defaults. Within the
resolved settings, `get_llm()` chooses the first matching route in the numbered order below.
`ace setup` clears competing route keys in `.env` when switching providers, but it cannot unset a
higher-priority value exported by the parent shell. `ace model-policy` shows the effective mapping;
`ace doctor` now reports configured-but-unverified routes without calling them, and
`ace doctor --live-provider` makes one explicitly requested minimal completion.

The ACE API bearer saved by `ace login` is separate from model-provider authentication. Codex and
Claude CLIs own their sign-in stores; ACE invokes them but never reads or copies those credentials.
API-key routes read only their named environment/`.env` settings. Router extras use the backend
credentials defined by their own SDKs.

## Frozen supported provider/authentication matrix

| # | Provider and route/auth mode | Configured model/tier and effort | Credential source | Live availability and expected diagnostic state | Runtime fallback and limitations |
|---:|---|---|---|---|---|
| 1 | LiteLLM router; explicit `LITELLM_MODEL` | Provider-prefixed default plus `LITELLM_MODEL_MAP`; effort is backend-defined and ACE reports `provider_default` | Router/backend environment | Not configured here; `configured_unverified` until an explicit live check | Optional extra; missing extra fails loudly. No fallthrough to another provider after selection. |
| 2 | AnyLLM router; explicit `ANYLLM_MODEL` | Provider-prefixed default plus `ANYLLM_MODEL_MAP`; effort is backend-defined and not asserted | Router/backend environment | Not configured here; `configured_unverified` until live check | Optional extra; missing extra fails loudly. LiteLLM wins if both router settings are present. |
| 3 | Ollama HTTP; local/self-hosted | `OLLAMA_MODEL` plus explicit map; ACE sends no assumed effort | No credential | No host configured here; configured route is unverified until probed | Missing host/model is `local_dependency_unavailable`/`unsupported_model`. No cross-provider substitution. |
| 4 | OpenAI-compatible HTTP; explicit base URL | `OPENAI_COMPAT_MODEL` plus map. Only exact `api.openai.com` GPT-5.6 routes accept ACE effort: `none`, `low`, `medium`, `high`, `xhigh`, `max`; `default` omits the field | `OPENAI_COMPAT_API_KEY` / `OPENAI_API_KEY`, or endpoint-defined/keyless | No API key here; `configured_unverified` until live check | Other compatible endpoints receive no guessed effort and report `provider_default`. `response_format` rejection gets one same-route retry only. |
| 5 | Codex CLI; ChatGPT subscription | Haiku→Luna, Sonnet→Terra, Opus/Fable→Sol. Effort supports `none`, `low`, `medium`, `high`, `xhigh`, `max`; `default` is omitted | Codex-managed sign-in | **Authenticated and live-reachable here**; passive state `authenticated`, explicit smoke state `reachable` | Stateless read-only subprocess. Timeout/cancellation terminates and reaps it. No OpenAI API billing or provider fallback. |
| 6 | Anthropic Messages API; metered key | Haiku, Sonnet, Opus, Fable remain distinct. Haiku receives no effort field; supported explicit Claude effort is `low` through `max`; `none` is rejected | `LLM_API_KEY` | No authorized key here; deterministic only | `REQUIRE_SUBSCRIPTION=1` rejects this route before billing. A 401 refresh occurs only for the opted-in rotating credential-store shape. |
| 7 | Anthropic Messages API; sanctioned Claude setup token | Same Claude tier/effort policy as row 6 | `CLAUDE_CODE_OAUTH_TOKEN` bearer | No authorized token here; deterministic only | Long-lived token is not reread after 401. No provider substitution. |
| 8 | Anthropic Messages API; opted-in credential-store token | Same Claude tier/effort policy | `~/.claude/.credentials.json`, only with `ALLOW_OAUTH_API_PATH=1` | Not enabled or inspected; unverified | Undocumented transport shape, off by default. This limitation is retained rather than promoted. |
| 9 | Claude CLI; subscription | Claude tiers passed through; provider-neutral semantic effort is added only where supported | Claude-managed sign-in | CLI absent here; `local_dependency_unavailable` if selected | Stateless subprocess; timeout/cancellation terminates and reaps it. JSON repair is bounded to three same-route attempts. |
| 10 | OpenAI HTTP from a bare ambient key; last-resort slot | Same known GPT mapping/effort behavior as row 4 | `OPENAI_COMPAT_API_KEY` / `OPENAI_API_KEY` | No API key here; deterministic only | Skipped by subscription-only/force-CLI safeguards. Deliberately below a usable Claude CLI. |
| 11 | Loud-fail empty Claude provider | Default Claude name, but no usable route | None | `not_configured` | First use fails; this is not a success or a fallback to another provider. |

The ordering is strict. Once a route resolves, request-time authentication, rate-limit, model,
effort, timeout, 4xx, 5xx, malformed-response, or streaming failures remain attributable to that
route. ACE does not re-enter the resolver and silently choose a different provider.

## Tier and effort behavior

| ACE role | Claude family | GPT family | Default effort behavior |
|---|---|---|---|
| Fast | Haiku | Luna | Omit override; Haiku is known not to receive an effort field |
| Capable | Sonnet | Terra | Omit override; provider adaptive/default behavior |
| Reasoning | Opus | Sol | Request `high` |
| Frontier | Fable | Sol | Request `xhigh` |

Fable is an ACE product-facing tier name in this implementation and resolves to the configured
Claude model string `claude-fable-5`; this report does not independently establish upstream Claude
catalog availability. GPT has three configured model tiers, so the two highest ACE roles share Sol
and remain distinct by requested effort. `max` is explicit-only. An unsupported configuration
value is rejected by settings validation; route-specific mismatches such as Claude `none` are
rejected before transport. For arbitrary OpenAI-compatible endpoints ACE omits effort rather than
claiming support.

Provider responses used by these adapters do not return an authoritative applied-effort field.
Diagnostics therefore record `requested_effort` and `effort_sent`, while `applied_effort` remains
`null`; this is intentional and prevents a false claim that the provider honored a setting it did
not echo.

## Live smoke evidence

| Route | ACE tier → resolved model | Requested / sent / applied effort | Latency | Usage | Result | Retry/fallback |
|---|---|---|---:|---|---|---|
| Codex CLI / ChatGPT subscription | Fast (Haiku) → `gpt-5.6-luna` | `default` / omitted / not reported | 3,222 ms | 6,832 input; 5 output; 0 reasoning-output tokens | `reachable` | One request; no retry; no fallback |
| Claude | — | — | — | — | **not run: no authorized Claude route available** | None |

The GPT smoke used `Reply with exactly OK.` through the hermetic completion adapter. Only the
structured diagnostic record above was retained; the credential and response text were not.
The resolved model is the adapter/CLI selection argument and was not independently echoed by an
upstream response-model field. The existing session was first checked with `codex login status`.

## Deterministic degraded-state coverage

Structured diagnostics distinguish `not_configured`, `configured_unverified`, `authenticated`,
`reachable`, `rate_limited`, `unauthorized`, `unavailable`, `timed_out`, `unsupported_model`,
`unsupported_effort`, `local_dependency_unavailable`, and
`provider_operational_but_degraded`. Every result names the failing layer, gives a next action, and
contains route metadata without credential values or raw upstream bodies.

Coverage includes:

- missing configuration and configured-but-unverified credentials;
- passive Codex authentication versus explicit live reachability;
- 401/403, 429, unrelated 4xx, model/effort rejection, and upstream 5xx classification;
- bounded diagnostic deadlines and subprocess termination on timeout or cancellation;
- malformed/empty responses as degraded rather than successful;
- GPT/Claude tier mapping, fast/capable defaults, explicit high/xhigh, GPT `none`, and Claude
  rejection of unsupported `none`;
- secret exclusion from Codex child environments, diagnostics, login failures, and tracked files;
- provider switching/configuration precedence and exact eleven-tool thin MCP registration.

The general `RetryPolicy` allows only 429/500/502/503/529 and caps the default loop at three
attempts. The OpenAI-compatible structured-output compatibility retry removes only a specifically
rejected `response_format` and retries once on the same route. CLI JSON repair retries at most
three times on the same route. `RetryPolicy.fallback_model`/`should_fallback()` are not wired into
provider execution, so ACE currently has **no supported explicit runtime fallback configuration**;
the honest behavior is attributable failure, not silent downgrade or cross-provider substitution.

## Changed behavior and limitations

- `ace doctor` no longer treats an environment variable or executable as proof of provider
  reachability. Default inspection is non-generative; `--live-provider` is explicit and labeled.
- Direct GPT-5.6 requests against exact `api.openai.com` now carry the ACE semantic effort when it
  is explicit. Compatible endpoints with unknown capabilities receive no assumed effort.
- Claude `none` effort fails before transport instead of being silently sent or claimed.
- CLI provider cancellation now reaps subprocesses.
- Login and doctor no longer echo raw upstream bodies or credential-bearing endpoint userinfo.
- The public MCP boundary remains exactly eleven thin client tools; no provider-specific tool was
  added.
- No live Claude evidence, no live metered OpenAI API evidence, and no live local/router evidence
  exist in this environment. These are not fabricated.

## Verification and remaining acceptance work

Local verification completed before the pull request:

| Gate | Result |
|---|---|
| Focused provider/authentication/doctor/kernel/MCP tests | **231 passed** |
| Exact kernel-boundary and eleven-tool tests | **60 passed** |
| Naked-kernel non-E2E suite | **6,102 passed, 213 skipped, 241 deselected**; four localhost-binding tests were denied by the sandbox |
| Sandbox-denied localhost tests, rerun with loopback permission | **4 passed** |
| Full non-E2E suite with loopback permission | No failures through **6,280 passed**; the local runner was interrupted after hanging during process teardown, so branch CI remains authoritative |
| Ruff lint and format | Passed; 1,761 files already formatted |
| Docker | Clean image build passed; configured container returned `{"status":"ok"}` from `/health/live` |
| Changed-file secret scan and `git diff --check` | Passed |

The Canvas source tree was not changed, so local Canvas-specific npm checks were not required. The
complete branch CI result is still pending and will be recorded in the pull request rather than
predicted here.

Before R3 can pass:

1. provide an already-authorized Claude API/setup-token/CLI route and run one minimal redacted live
   smoke through `ace doctor --live-provider`;
2. record the Claude resolved model, requested/sent/applied-effort truth, latency, usage metadata,
   and failure/retry behavior without retaining response or credential content;
3. complete branch CI and reconcile its URL/results here and in the public roadmap;
4. review any overlap after further R1 changes, then update from main if necessary.

R4 remains dependency-closed until that evidence exists and R3 is reconciled to `passed`.
