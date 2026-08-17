# ACE host first run — authoritative UX extension

Status: **UX candidate for the official ACE 1.1 Code Intelligence integration; production host contract not yet implemented**  
Relationship: extension of the selected Atrium onboarding, not a separate onboarding framework or release track  
Owner for integration acceptance: ACE 1.1 Code Intelligence control tower

## Product decision

ACE first run has one universal material question:

> How should ACE run on this computer?

An unconfigured host offers three explicit operating boundaries:

| Mode | Product meaning | Universal first-run effect |
|---|---|---|
| **Personal** | Default for an ordinary laptop or workstation; ACE runs on demand beside the owner's applications and may unload the model while idle. | Recommended only when host detection supports that recommendation and no administrator override exists. Local-only access remains the default. |
| **Shared server** | ACE coexists with other workloads; resource ceilings, authentication, and an operator boundary matter. | Records the boundary. It does not enable remote access or ask universal users to configure operators, networking, or retention. |
| **Dedicated appliance** | The computer is exclusively ACE; boot startup, recovery, private remote access, and an optional local status console may be appropriate. | Records intent only. Appliance conversion is a separate, explicit, reviewed flow; no system mutation runs here. |

Detected hardware, runtime, model profile, quantization, practical context, and hardware-specific expectation appear as a status summary, not six more questions. A user-owned selection is inspectable and changeable later in Settings without reinstalling. An environment- or administrator-fixed selection is shown later as fixed and is not mutable by an ordinary user.

## Reconciliation with the accepted Atrium journey

Host first run is a thin pre-Atrium gate. It does not replace the accepted **Choose → Intent → Evidence → Review → Activate** intelligence journey.

```text
host projection
  ├─ configured or administrator-fixed → Atrium immediately
  └─ genuinely unconfigured
       → detect hardware/runtime/current configuration
       → ask one operating-mode question
       → persist and re-read the exact mode
       → Atrium immediately
            → “What should ACE understand?” / first real outcome
            → generated intelligence blueprint
            → source/evidence/review/activation journey

background, nonblocking runtime lane
  recommended model download → model loaded → real generation smoke test
```

The application must not wait for a large model download before entering Atrium. “ACE usable now,” “recommended model downloading,” “model loaded,” and “a real generation test passed” are four independent truths. A running model process or healthy HTTP endpoint is never relabeled as successful generation.

## Universal surface and contextual branches

Universal first run includes only:

1. automatic detection and existing-configuration lookup;
2. the three operating-mode cards when no persisted or fixed mode exists;
3. a detected, editable-later model/context recommendation;
4. a local-only security boundary; and
5. immediate entry into Atrium after durable persistence is re-read.

The following stay out of universal first run: boot behavior, auto-login, hostname, Tailscale or other remote access, destructive cleanup, retention, migration/import, multi-user administration, console behavior, and advanced model/context tuning.

Dedicated appliance conversion is a separate operator flow. Any cleanup follows **backup → quarantine → verify → separately approved deletion**. Private remote exposure is a separate consent action and may warn about temporary connectivity interruption. Personal and Shared first run never invoke appliance-only service, boot-target, console, hostname, or pruning mutations.

## Reference lock

The extension reuses the selected A+C tokens, shadcn/Radix primitives, and Lucide family. It adds no new visual vocabulary.

| Reference role | Preserved pattern | Rejected interpretation |
|---|---|---|
| [Tailscale infrastructure clarity](https://tailscale.com/kb/1325/device-web-interface) | Compact literal status, explicit access boundary, local-first posture | Network enablement hidden inside setup |
| [OpenAI Developers restraint](https://developers.openai.com/api/docs/models) | Quiet technical facts, short labels, neutral hierarchy | Dense admin console or decorative AI treatment |
| [Typeform choice clarity](https://help.typeform.com/hc/en-us/articles/360051789692-Question-types) | Three unmistakable, keyboard-operable choice cards | Long account survey or ambiguous chips |
| [Miro one-question focus](https://help.miro.com/hc/en-us/articles/360017730533-What-is-Miro) | One material decision with progressive detail | Tutorial carousel or multi-step interrogation |

The locked visuals are:

- [`atrium-host-first-run-1440x960.png`](atrium-product-ux-directions-v1/implementation/atrium-host-first-run-1440x960.png)
- [`atrium-host-first-run-390x844.png`](atrium-product-ux-directions-v1/implementation/atrium-host-first-run-390x844.png)
- [`atrium-host-runtime-arrival-1440x960.png`](atrium-product-ux-directions-v1/implementation/atrium-host-runtime-arrival-1440x960.png)

## Candidate host contract for control-tower construction

This is a contract assumption, not a claim of a production endpoint in this worktree.

### Read projection

A host-owned first-run projection must distinguish exactly:

- `configured`: durable user-owned mode exists;
- `admin_fixed`: environment/administrator owns the durable mode and ordinary users cannot change it; or
- `unconfigured`: no durable mode exists, with detected environment facts and an optional `personal` recommendation.

The projection also needs:

- exact configuration ownership/source and mutability;
- usable RAM, compute/runtime availability, and relevant runtime ownership;
- Docker Compose v2 and system-vs-user ownership where applicable;
- model profile, quantization, practical context, and explanation/expectation;
- local/remote exposure state without inferring reachability from process health;
- download bytes/state/resumability and offline/low-disk diagnostics;
- model-loaded state; and
- separately recorded real-generation smoke-test state.

### Persist selection

The mutation must accept only one exact mode plus a stable request/idempotency key. The host authenticates and authorizes the local owner, persists append-only or equivalently audit-safe configuration material, and returns/re-reads the canonical projection. Replaying identical material returns the same result; crossed material under the same key fails closed. A resolved client promise is not proof of persistence, so the candidate UI remains pending until the host supplies a `configured` projection.

Changing a user-owned mode later uses the same authority and persistence system from Settings. It must not reinstall ACE. Administrator-fixed state rejects ordinary-user mutation. No mutation may silently enable remote serving.

### Runtime readiness

The background runtime projection must preserve these independent states:

| Truth | Valid evidence |
|---|---|
| ACE usable now | Host proves that a usable current execution path exists; it may be a smaller/previous local profile or another configured provider. |
| Model download | Exact lifecycle and, when known, byte progress; interruption/error and resumability are explicit. |
| Model loaded | Runtime proves the selected model is loaded. This does not imply generation success. |
| Generation check | A real inference request completed successfully for that exact profile/runtime. Health endpoints and process presence do not qualify. |

The download manager must survive interruption/restart, check disk capacity, preserve partial material safely, and expose offline, checksum, and runtime-load errors. Reduced motion removes indeterminate animation; it never removes state or progress text.

## Existing-runtime reuse and dependencies

`core/engine/cli/commands/setup.py` is the relevant existing setup path. It already contains useful seams for provider/runtime detection, Docker Compose v2 detection with legacy fallback, service startup, and idempotent local-owner bootstrap. Integration should adapt those seams behind one host projection/persistence boundary rather than create a competing onboarding service.

The existing path is not sufficient for this acceptance because it currently relies on service/health readiness and does not prove a real generation. Production routing is intentionally not changed in this UX worktree because the following contracts are absent:

1. a host first-run read projection available early enough to gate Atrium;
2. durable mode persistence, ownership, mutability, and Settings mutation;
3. resumable model-download lifecycle with disk/offline truth;
4. exact model-loaded and real-generation smoke-test receipts;
5. a supported renewable local/device credential or explicit appliance auth mode;
6. a separate reviewed appliance-conversion workflow; and
7. browser-test fixtures backed by those accepted API shapes.

The local-owner bootstrap must remain automatic, idempotent, restart-safe, and recoverable. Avoid restart-based login workarounds.

## Deployment evidence boundary

On one tested 32 GB UM790 appliance, a Qwen3.8 27B GGUF profile at roughly Q4-class quantization was viable at an observed approximately 2.9 tokens/second with a configured 65,536-token context. This is deployment evidence, not a product promise or a universal recommendation. The UI says hardware-specific expectations require a smoke test. It also explains that ACE's context/memory stack optimizes what enters the active model window; it does not imply that a small machine should keep a million-token live prompt.

## Accessibility, responsive, and recovery contract

- The question receives programmatic focus only on a genuinely unconfigured first run.
- The three cards form one named Radix radio group with arrow-key and tab semantics.
- Recommended state is text, not color alone; icons are decorative to assistive technology.
- Pending persistence disables the complete group and retains truthful copy until a configured projection arrives.
- Persistence failure returns focusable controls and an announced alert.
- Runtime updates are polite live-region content with an accessible native progressbar when exact byte totals exist.
- The 390×844 state preserves all three choices and local-only truth; detected technical detail may collapse, but no truth changes.
- Offline, low-disk, interrupted/resumable download, download failure, load failure, and smoke-test failure remain literal and recoverable where the host contract supports recovery.
- Reduced motion changes motion only, never the state model.

## Decision ledger

| Decision | Included | Intentionally rejected |
|---|---|---|
| Journey placement | Pre-Atrium gate for unconfigured hosts, then the existing first real outcome | A second onboarding product or tutorial after mode selection |
| Question count | One material operating-boundary question | Provider/model/context/account survey |
| Recommendation | Detected status, editable later | Interrogating users for advanced tuning |
| Personal default | Preselected only from an honest host recommendation and no admin override | Universal hard-coded default regardless of host |
| Configured/fixed hosts | Bypass prompt; fixed ownership remains immutable to ordinary users | Re-onboarding every install |
| Download | Background, resumable, exact progress/error truth | Blocking Atrium on a large download |
| Readiness | Separate usable/downloaded/loaded/generated truths | “Process running” or `/health` means ready |
| Exposure | Local-only until separate explicit operator action | Silent private/public network exposure |
| Appliance | Explicit later conversion and reviewed mutations | Running boot/login/hostname/cleanup actions from first run |
| Visual system | A+C monochrome, Radix/shadcn, Lucide | Generic gradients, repeated shield icons, second icon vocabulary |

## Acceptance disposition

The reusable unmounted candidate component and its focused tests cover the projection union, bypass, recommendation, selection/pending/failure, semantic choice group, detected status, local-only boundary, and four-part readiness truth. Static desktop/narrow/runtime-arrival artifacts cover the intended composition.

Production routing, API/unit persistence tests, Settings mutation, live download/smoke behavior, and end-to-end browser visual tests remain **control-tower integration dependencies**. No separate-worktree artifact or unit pass constitutes ACE 1.1 integrated acceptance. RAG/search code and behavior are unchanged.
