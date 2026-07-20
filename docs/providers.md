# Providers — Bring Your Model

How ACE resolves an LLM backend, how to configure each one, what each path
bills, and how to add a new provider. The authority for the resolution order
is the `get_llm()` docstring in
[`core/engine/core/llm.py`](../core/engine/core/llm.py); this page is the
operator-facing rendering of it.

Everything below routes through one call: `get_llm()` returns an object
satisfying the `LLMProvider` Protocol (`complete`, `complete_json`,
`stream`, `stream_messages`, `complete_structured`). Engine code never
imports a concrete provider.

## Access principle

ACE is designed for three kinds of access:

1. **Subscription-backed shell or agent:** use an eligible subscription through a documented,
   sanctioned CLI/SDK/agent surface. This may be slower or more constrained than direct HTTP.
2. **Metered API key:** direct provider access for speed, throughput, and automation.
3. **Local/self-hosted:** private inference through Ollama or an OpenAI-compatible local endpoint.

Consumer subscriptions are not generic API credentials. ACE never scrapes browser sessions,
keychains, or undocumented consumer tokens. ChatGPT-plan access is integrated through a sanctioned
Codex adapter rather than treated as OpenAI API credit; general OpenAI API billing remains
separate. Claude subscription access similarly uses the documented setup-token/Agent SDK or CLI
paths described below.

The long-term contract is access-class parity where technically possible: every user gets ACE's
persistent reasoning and decision layer, while diagnostics disclose differences in speed, limits,
tool support, and billing.

After configuring a route, inspect the effective semantic policy without exposing credentials:

```bash
ace model-policy
ace doctor
```

`ace model-policy` reports the selected access class, fast/capable/reasoning/frontier role mapping, privacy,
cost, availability, concurrency, escalation, fallback, context-limit posture, and any validation or
degradation findings. `ace doctor` additionally verifies the database, schema, API, protected
authentication request, provider configuration, and exact eleven-tool thin MCP registration.

## The resolution chain

`get_llm()` walks eleven slots in priority order and returns the first match.
Explicit configuration always outranks ambient credentials.

| # | Trigger | Provider | Billing semantics | Safeguards that affect it |
|---|---------|----------|-------------------|---------------------------|
| 1 | `LITELLM_MODEL` set | `LiteLLMProvider` (optional `ace[litellm]` extra) | Metered, to whatever backend the model string names; ledger rows `source="litellm"`, `billing="metered_estimate"` | None — explicit setting is deliberate intent; exempt from `REQUIRE_SUBSCRIPTION` and `FORCE_CLI_PROVIDER` |
| 2 | `ANYLLM_MODEL` set | `AnyLLMProvider` (optional `ace[any-llm]` extra) | Metered; ledger rows `source="anyllm"`, `billing="metered_estimate"` | Same exemptions as slot 1. If both router models are set, litellm wins and a warning logs |
| 3 | `OLLAMA_HOST` set | `OllamaProvider` | Local inference — free; no ledger rows | None |
| 4 | `OPENAI_COMPAT_BASE_URL` set | `OpenAICompatProvider` | Metered to the configured backend; ledger rows `source="openai_compat"`, `billing="metered_estimate"` | Exempt from `REQUIRE_SUBSCRIPTION` (explicit base_url) and `FORCE_CLI_PROVIDER` |
| 5 | `SUBSCRIPTION_PROVIDER=codex` | `CodexCLIProvider` (`codex exec`) | ChatGPT subscription capacity; ledger rows `source="codex_cli"`, `billing="chatgpt_subscription"`, `cost_usd=0` because no Platform API charge is made | Explicit selection; Codex CLI must be installed and signed in. ACE never reads Codex's credential store |
| 6 | `LLM_API_KEY` looks real (not `sk-test*`, not `sk-ant-...`, length > 20) | `ClaudeProvider` (`x-api-key`) | **Metered Anthropic API** — pay per token | `REQUIRE_SUBSCRIPTION=1` → refused with a `RuntimeError` (no silent billing). NOT skipped by `FORCE_CLI_PROVIDER` |
| 7 | `CLAUDE_CODE_OAUTH_TOKEN` set | `ClaudeProvider` (`Authorization: Bearer` + `anthropic-beta: oauth-2025-04-20`) | Subscription pool — same monthly Agent SDK credit as the CLI; no per-call dollars | Skipped by `FORCE_CLI_PROVIDER=1` |
| 8 | `ALLOW_OAUTH_API_PATH=1` AND an OAuth access token in `~/.claude/.credentials.json` | `ClaudeProvider` (OAuth token as `x-api-key`) | Subscription — **undocumented shape**, off by default | Opt-in only (`ALLOW_OAUTH_API_PATH=1`); skipped by `FORCE_CLI_PROVIDER=1` |
| 9 | `claude` CLI in `PATH` (or `~/.local/bin`, `/usr/local/bin`, `/opt/homebrew/bin`) | `CLIProvider` (subprocess per call) | Subscription — `claude -p`-shaped, draws the monthly **Agent SDK credit** from June 15 2026; ledger rows `source="cli_provider"`, `billing="subscription_credit_estimate"` | This is the path `FORCE_CLI_PROVIDER=1` forces |
| 10 | `OPENAI_COMPAT_API_KEY` set, with no Anthropic credentials and no usable CLI | `OpenAICompatProvider` against `https://api.openai.com/v1` | Metered OpenAI | Skipped by `REQUIRE_SUBSCRIPTION=1` and by `FORCE_CLI_PROVIDER=1`. Deliberately BELOW the CLI: a stray key export must never outrank a working subscription |
| 11 | Nothing matched | Empty `ClaudeProvider` | None — errors loudly on first use | — |

> **Alias note:** the four `OPENAI_COMPAT_*` settings also read the plain
> `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_MODEL_MAP`
> names (industry convention — copy-pasted configs and ambient
> `OPENAI_API_KEY` exports keep working). When both forms are set, the
> canonical `OPENAI_COMPAT_*` name wins.

Two design rules behind the ordering:

- **Slots 1–4 are explicit intent.** They activate only via a setting the
  operator wrote down (`LITELLM_MODEL`, `ANYLLM_MODEL`, `OLLAMA_HOST`,
  `OPENAI_COMPAT_BASE_URL`) — never via ambient credentials — so the
  safeguards don't second-guess them.
- **Slot 5 is an explicit subscription selection.** It does not infer ChatGPT
  access from an ambient OpenAI key.
- **Slots 6–10 are credential- or executable-triggered**, which is exactly what the
  safeguards exist to police: an accidentally exported key must not
  silently bill a metered API.

`LLM_API_KEY` is route-specific, not a universal startup requirement. If it is
unset, ACE treats it as no Anthropic API credential and continues through the
explicit local, compatible-endpoint, router, subscription-token, and CLI
slots. The `.env.example` placeholder documents that fallthrough and is never
accepted as a usable provider.

## Configuring each path

### ChatGPT subscription via Codex CLI

Sign Codex in through its documented ChatGPT browser flow, verify the session,
then explicitly select the route:

```bash
codex login
codex login status
export SUBSCRIPTION_PROVIDER=codex
export CODEX_CLI_MODEL=gpt-5.6-terra
export CODEX_CLI_EFFORT=medium
export REQUIRE_SUBSCRIPTION=1
```

ACE does not read or copy Codex's cached credentials. Each call uses an ephemeral,
read-only `codex exec` process with workspace rules, tools, apps, hooks, memories,
and web search disabled. Prompts are sent over stdin, and unrelated ACE/provider
secrets are excluded from the child environment. This route uses ChatGPT-plan
capacity; it does not turn a ChatGPT subscription into OpenAI Platform API credit.
For metered OpenAI API automation, configure the OpenAI-compatible route instead.

`SUBSCRIPTION_PROVIDER=auto` is the default and preserves Claude-first resolution;
`SUBSCRIPTION_PROVIDER=claude` states that preference explicitly. The selector
does not override explicitly configured router, local, or base-URL routes.

### Subscription via setup-token (recommended for headless/CI)

The sanctioned subscription-programmatic shape. Generate a long-lived
(one-year, inference-only) token and export it:

```bash
claude setup-token            # prints a token
export CLAUDE_CODE_OAUTH_TOKEN=<token>
export LLM_API_KEY=sk-test-placeholder   # optional placeholder; falls through
```

No subprocess per call (it is direct HTTP to the Messages API), but it bills
the same subscription pool as the CLI. The token is long-lived and is not
re-read from disk on a 401.

### Subscription via the `claude` CLI

Zero config: if the `claude` binary is installed and authenticated, slot 8
activates automatically. Every call is a hermetic subprocess
(`--no-session-persistence --tools ""`, neutral cwd, project/local setting
sources only) — slower than HTTP, but fully sandboxed from hooks and MCP.
Prefer slot 7 for headless or high-volume Claude runs.

### Metered Anthropic API key

```bash
export LLM_API_KEY=sk-ant-api03-...
```

Direct API, fastest, **pay-per-token**. Default models come from settings:
`LLM_MODEL` (default `claude-sonnet-5`), `LLM_BUDGET_MODEL`
(`claude-haiku-4-5-20251001`), `LLM_REASONING_MODEL` (`claude-opus-4-8`),
and `LLM_FRONTIER_MODEL` (`claude-fable-5`).
This is the only provider that passes cache-control system blocks through
verbatim — multiphase `stable_prefix` prompt caching depends on it.

### Ollama (local)

```bash
export OLLAMA_HOST=http://localhost:11434   # or a LAN box
export OLLAMA_MODEL=llama3.2                # default model (optional)
export OLLAMA_MODEL_MAP='{"claude-haiku-4-5-20251001": "llama3.2:3b", "claude-sonnet-5": "llama3.3"}'
```

Free, local, no key. No built-in tier map — a local box serves whatever the
operator pulled, so set `OLLAMA_MODEL_MAP` for tiered routing (see
[Tier maps](#tier-maps-and-unknown-model-grace)).

### OpenAI-compatible backends (zero-dep, in core)

One provider covers OpenAI, Azure, Groq, Together, OpenRouter, vLLM,
LM Studio, and Ollama's compat endpoint — anything serving
`POST {base_url}/chat/completions`:

```bash
export OPENAI_COMPAT_BASE_URL=https://api.groq.com/openai/v1
export OPENAI_COMPAT_API_KEY=gsk_...               # optional — vLLM/LM Studio often run keyless
export OPENAI_COMPAT_MODEL=llama-3.3-70b-versatile # default model (default: gpt-5.6-terra)
export OPENAI_COMPAT_MODEL_MAP='{"claude-opus-4-8": "gpt-5.6-sol"}'
```

The names say `OPENAI_COMPAT_*` because the provider speaks OpenAI's **wire
format** to any backend — the format is not the vendor (a Gemini or Groq
endpoint configured here is not "an OpenAI model"). The plain `OPENAI_*`
forms work as aliases; canonical wins when both are set.

Built on `httpx` (an existing dependency) — no openai SDK. `complete_json` /
`complete_structured` send `response_format` and fall back to prompt-based
JSON on a 400 **that names `response_format`** (many compat servers reject
the parameter); all other errors propagate untouched. A bare
`OPENAI_COMPAT_API_KEY` with no base_url means OpenAI itself — but only as
slot 9, the last resort before the loud fail.

### litellm router (optional extra)

```bash
pip install 'ace-core[litellm]'   # or: uv sync --extra litellm
export LITELLM_MODEL=groq/llama-3.3-70b-versatile
export LITELLM_MODEL_MAP='{"claude-haiku-4-5-20251001": "groq/llama-3.1-8b-instant"}'
```

100+ providers via litellm's `provider/model` strings — that syntax IS the
tier map for power users. When `LITELLM_MODEL` targets Anthropic
(`anthropic/...`), the four Claude tiers map to their prefixed forms out of
the box; any other target starts with an empty map (no silent re-routing to
a billing target the operator didn't choose) until `LITELLM_MODEL_MAP` says
otherwise.

**Security caveat — why this is an extra, not a core dep:** the March 2026
PyPI supply-chain compromise of litellm itself (1.82.7/1.82.8 shipped a
credential stealer + RCE) and CVE-2026-42208 (pre-auth SQLi, CVSS 9.3,
exploited in the wild within 36 hours of disclosure). The extra pins
`litellm>=1.83.7` (the SQLi fix) — never resolve below it. litellm's
advisory cadence is roughly monthly; adopt with eyes open.

### any-llm router (optional extra)

```bash
pip install 'ace-core[any-llm]'   # or: uv sync --extra any-llm
pip install 'any-llm-sdk[anthropic]'   # the backend named by your provider prefix
export ANYLLM_MODEL=anthropic/claude-sonnet-5
export ANYLLM_MODEL_MAP='{"claude-haiku-4-5-20251001": "groq/llama-3.1-8b-instant"}'
```

Mozilla AI's router (Apache-2.0 — license-matched to ACE, clean
vulnerability record) — the second extra exists so adopters can pick their
risk posture. ACE config keeps one string (`provider/model` or
`provider:model`); the adapter splits the prefix and passes `provider=` and
`model=` separately to the SDK. Same Anthropic-prefix tier defaults and
empty-map discipline as litellm.

If **both** `LITELLM_MODEL` and `ANYLLM_MODEL` are set, litellm wins and a
warning logs. Both extras are lazy-imported: the default install never
imports them, and activating a router setting without the extra installed
raises an actionable `pip install 'ace-core[...]'` error instead of silently
falling through to a differently-billed backend.

## June 15 2026 — Agent SDK credit semantics

Starting **June 15 2026**, Agent SDK and `claude -p` (non-interactive) usage
on subscription plans draws from a monthly **Agent SDK credit** — Pro $20 /
Max 5x $100 / Max 20x $200 — separate from interactive limits. When the
credit is exhausted, usage **hard-stops** unless usage credits (API-rate
overage) are enabled on the account. The sanctioned
subscription-programmatic shapes are Claude Code, the Agent SDK, and
`claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`.

What this means for ACE:

- **Slots 7 and 9 both draw this credit.** ACE's CLIProvider is
  `claude -p`-shaped; the setup-token bearer bills the same pool without the
  subprocess.
- **Cost posture:** route machine-triggered work (sentinel loops, foresight,
  scheduled scans) to local/cheap backends — Ollama, or the haiku tier on a
  mapped provider — and keep human-triggered reasoning on frontier models
  drawing the credit. The per-call ledger (below) is what makes the draw
  observable; the machine-vs-human trigger split in ledger rows is a noted
  follow-up.
- Slot 8 (OAuth-as-API) is gated off by default because Anthropic publishes
  no sanction for that shape — not because it is known to be blocked.

## Safeguard matrix

| Safeguard | Effect on the chain |
|---|---|
| `REQUIRE_SUBSCRIPTION=1` | Slot 6 **refused** (clear `RuntimeError` with remediation options); slot 10 **skipped**. Slots 1, 2, 4, and the explicit ChatGPT subscription slot 5 are unaffected |
| `FORCE_CLI_PROVIDER=1` | Claude slots 7, 8, and 10 **skipped** — the resolver lands on the Claude CLI subprocess (slot 9). Does not override explicit router/local/base-URL/Codex selection or a real metered Anthropic key |
| `ALLOW_OAUTH_API_PATH=1` | **Enables** slot 8 (off by default) — the undocumented OAuth-as-API shape, lifted from `~/.claude/.credentials.json` and sent as `x-api-key`. Opt in only if you have verified it in your environment and accept the unsupported-shape risk |

## Tier maps and unknown-model grace

ACE call sites route cost-aware by passing its current Claude vocabulary —
`claude-haiku-4-5-20251001` / `claude-sonnet-5` / `claude-opus-4-8` /
`claude-fable-5` (from `LLM_BUDGET_MODEL` / `LLM_MODEL` /
`LLM_REASONING_MODEL` / `LLM_FRONTIER_MODEL`). That caller
vocabulary is deliberately stable; **providers translate at request time**
via `ModelMapMixin` (`core/engine/core/llm.py`):

1. Mapped name → the provider-native model from the `*_MODEL_MAP` setting.
2. Unmapped `claude*` name → the provider's default model, with a
   **one-time warning per (provider, name) per process** naming the setting
   that fixes it. Tier routing degrades visibly, never crashes.
3. Anything else → passed through verbatim (a native model name is
   deliberate caller intent).

Map settings are JSON dicts in env (`OLLAMA_MODEL_MAP`,
`OPENAI_COMPAT_MODEL_MAP`, `LITELLM_MODEL_MAP`, `ANYLLM_MODEL_MAP`,
`CODEX_CLI_MODEL_MAP`) and
**merge over** each provider's
built-in defaults, so one entry can re-point a single tier. Built-in
defaults exist only where the catalog is known:

- `CodexCLIProvider` and `OpenAICompatProvider` targeting `api.openai.com`:
  Haiku → `gpt-5.6-luna`, Sonnet → `gpt-5.6-terra`, and both Opus and
  Fable → `gpt-5.6-sol`. GPT has three current native tiers, so ACE records
  the distinct semantic role even when its two highest roles share Sol.
- `LiteLLMProvider` / `AnyLLMProvider`, only when the configured default
  model targets Anthropic: the four Claude tiers map to their
  `anthropic/`-prefixed forms (same billing target the operator chose).
- `CODEX_CLI_MODEL` is the fallback/default (`gpt-5.6-terra`); the built-in
  tier map above remains active unless overridden in `CODEX_CLI_MODEL_MAP`.

Model family and reasoning effort are independent controls on both native routes.
Fast and Capable omit an effort override so the provider can use its adaptive
default; Reasoning uses high and Frontier uses xhigh. Max is reserved for an
explicit override rather than spent automatically. On GPT this means the two
highest ACE roles share Sol without receiving the same inference budget. Override
Codex roles with `CODEX_CLI_EFFORT_MAP`; `CODEX_CLI_EFFORT` is the fallback for an
unmapped native/custom model. `default` omits the Codex setting entirely; explicit
Codex values are `none`, `low`, `medium`, `high`, `xhigh`, and `max`.

The provider-neutral settings `LLM_BUDGET_EFFORT`, `LLM_EFFORT`,
`LLM_REASONING_EFFORT`, and `LLM_FRONTIER_EFFORT` drive Anthropic API and Claude
CLI calls. Claude Haiku receives no effort flag because the current model does not
support one; Sonnet uses the provider default, Opus uses high, and Fable uses xhigh.
Explicit supported Claude values are `low`, `medium`, `high`, `xhigh`, and `max`.
This is a routing analogue, not evidence of cross-provider quality equivalence;
M5 must measure the routes separately.

Anthropic-native providers (`ClaudeProvider`, `CLIProvider`) pass tier names
through untouched while applying the independent effort policy above.

## Usage persistence — what writes the ledger

Per-call usage persists fail-open to SurrealDB's `token_ledger_entry` table
(`core/engine/intelligence/token_ledger.py`). A DB failure never breaks an
LLM call.

| `source` | Written by | `billing` | Notes |
|---|---|---|---|
| `executor` (or absent on legacy rows) | Task-level accumulator (executor) | — | One row per completed task |
| `cli_provider` | `CLIProvider`, one row per call | `subscription_credit_estimate` | `cost_usd` is the CLI's own API-rate-equivalent `total_cost_usd` (the best estimate of the Agent SDK credit draw), falling back to `model_costs.cost_for_call` |
| `codex_cli` | `CodexCLIProvider`, one row per call | `chatgpt_subscription` | Native token usage; `cost_usd=0` means no metered OpenAI Platform API charge, not that the ChatGPT plan has no subscription cost or capacity limits |
| `openai_compat` | `OpenAICompatProvider`, per call | `metered_estimate` | `cost_usd` from `model_costs.cost_for_call` |
| `litellm` | `LiteLLMProvider`, per call | `metered_estimate` | Prefers litellm's own `response_cost` figure when present |
| `anyllm` | `AnyLLMProvider`, per call | `metered_estimate` | No SDK cost figure; `cost_for_call` only |

Billing labels: `subscription_credit_estimate` means no dollars were billed
for the call — the figure estimates the draw against the monthly
subscription credit. `metered_estimate` means a metered API was billed and
the figure is ACE's estimate of it. The bounded rates table
(`core/engine/core/model_costs.py`) covers the current Claude and GPT
families plus retained historical Claude models. Other wire models record
`cost_usd=0.0` with a debug log — honest unknown-model grace, not a crash.

**Aggregation scoping:** task-level analytics (`TokenLedger.get_summary`,
`get_passes_by_discipline`, `get_weekly_trend`, the contributions
aggregator) filter to executor rows (`source = NONE OR source IS NULL OR
source = 'executor'`) — per-call provider rows describe the *same underlying
spend* the executor accumulator summarizes, and mixing them would
double-count cost and report raw LLM calls as tasks. Per-call rows are for
spend observability (the June-15 credit draw); executor rows are for task
economics. `OllamaProvider` and the direct `ClaudeProvider` HTTP paths write
no per-call rows (Ollama is free; ClaudeProvider feeds the in-process token
accumulator that produces executor rows).

## Writing your own provider — the conformance suite is the contract

The `LLMProvider` Protocol checks signatures; the conformance suite
([`tests/llm/conformance.py`](../tests/llm/conformance.py)) checks
**behavior**. Every provider — including third-party ones — must pass the
same 16 behavioral contracts: text completion with model/max_tokens
honored, `system` as string AND cache-block list (flattened where the
backend lacks cache support — every block's text must reach the transport),
JSON discipline (instruction appended, fences stripped,
`json.JSONDecodeError` on garbage), structured-output round-trip,
incremental streaming, empty-response handling, and tier-name translation
through the provider's model map.

Wiring a new provider is one small test class: subclass
`LLMConformanceSuite`, set `default_model` / `override_model`, implement the
six transport hooks (`make_provider`, `respond_text`, `respond_empty`,
`respond_stream`, `last_request`, `transport_calls`), and set any divergence
knobs **with a reason** (e.g. the CLI retries empty responses 3x; HTTP
providers don't). The full hook contract and knob list live in the module
docstring. Hooks speak in normalized `CapturedRequest` terms — nothing in
the suite assumes chat-completions is the only wire shape (the
vendor-neutral Responses API can be added later without rewriting it).

No live network in unit tests: mock the transport (httpx transport, SDK
monkeypatch, or subprocess stub per the existing wirings in `tests/llm/`).
