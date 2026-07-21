# IA-R1 — read-only product-map information architecture

**Outcome state:** implementation candidate; branch/final-head/main CI and roadmap closeout pending

**Evidence date:** 2026-07-21

**Operator journey:** Canvas → **Product map** → `/landscape`

**Data contract:** authenticated `GET /product/landscape` with
`ace.living-product-projection.g1.v1`

## Outcome

IA-R1 defines the smallest operator-usable information architecture over G1's Living Product
Graph read contract. It gives a person one bounded place to answer six questions:

1. What exists?
2. How does it connect?
3. Why do we believe it?
4. What changed?
5. What happened next?
6. What needs attention?

The view is an inspection surface, not a graph editor, workflow runner, chat prompt, or second
roadmap. It adds no graph mutation, decision mutation, execution, autonomous dispatch, extension,
model-inference, assertion-resolution, or Atrium write authority.

## As-built audit

The audit started from `origin/main` after G1 and R4 passed. G1 already supplied the versioned,
bounded, deterministic, product-scoped snapshot. R4 supplied durable public decision, correction,
restart, and later-use evidence. Canvas already supplied authenticated reads, shared navigation and
layout primitives, and experimental Atrium/Board/Showcase surfaces. It did not expose the G1 read
or provide an operator hierarchy across those records.

| Operator need | Before IA-R1 | Reused authority | Gap | IA-R1 treatment |
|---|---|---|---|---|
| Find the whole-product view | CLI `ace landscape`; no Canvas destination | G1 snapshot only | No discoverable visual route | Kernel nav item and `/landscape` route named **Product map** |
| Know what exists | Raw snapshot families | G1 stable identities and product scope | Operators had to understand storage-family names | Intent, projects, and capabilities grouped under **What exists** |
| Distinguish truth from proposals | Operational and assertion arrays were separate but structural | G1 accepted-only operational projection | Visual treatment could accidentally flatten status | Current relationships separate from accepted, provisional, contested, rejected, and unknown assertions |
| Inspect grounds | Evidence refs, confidence, contradiction refs, explanation, provenance | G1 assertion contract | No operator-facing hierarchy | **Why we believe it** retains status, evidence count, contradictions, confidence, explanation, and stable ID |
| Follow change | Decisions, correction observations, assertion events | G1 projection plus R4 artifacts | Records were in separate families | **What changed** keeps decisions, explicit corrections, and assertion history distinct |
| Separate prediction from result | Predictions and multiple outcome families | G1 foresight projection | Easy to read a prediction as an outcome | **What happened next** has separate prediction and observed-outcome lanes |
| See incomplete reads | Projection status, issues, source receipts, recovery | G1 failure contract | Missing data could look like zero data | Non-complete banner, attention count, issue recovery, source status/reason/count/limit |
| Confirm scope and replay | Product ID, snapshot ID, schema/projection versions | G1 identity contract | Receipt was not visible in Canvas | Header product identity and footer snapshot/version receipt |
| Avoid accidental action | No dedicated read-only page existed | G1 GET route and authority object | Adjacent Canvas surfaces contain writes | No domain action controls; only the authenticated GET and a GET retry |

No new backend route, database query, record family, MCP tool, extension hook, or model call was
needed. The implementation composes the existing G1 response and leaves the exactly eleven-tool
thin MCP boundary unchanged.

## Frozen information architecture

The hierarchy is question-led rather than storage-led:

| Order | Section | Records | Invariant |
|---|---|---|---|
| Header | Product and snapshot orientation | product, authority, projection state | Always says read-only and names non-authority |
| Summary | At a glance | projects, capabilities, decisions, operational relationships, attention | Counts index the snapshot; they are not a health score |
| 1 | What exists | direction, vision, project, capability | Missing families say absent from this snapshot, not absent from reality |
| 2 | How it connects | operational relationships plus assertion-state counts | Only accepted and projection-eligible truth appears as current |
| 3 | Why we believe it | relationship assertions | Dissent and rejection remain visible and non-operational |
| 4 | What changed | decisions, correction observations, assertion events | Corrections are not rewritten into decisions; history is append-only inspection |
| 5 | What happened next | predictions and observed outcome families | Expected and observed results never collapse |
| 6 | What needs attention | issues and source receipts | Unknown, partial, degraded, and unavailable stay explicit with recovery context |
| Footer | Replay receipt | snapshot/schema/projection IDs | Stable identity remains copyable and inspectable |

Rows are capped visually at six per content lane while the G1 response itself retains its
documented 256-record per-family bound. Available source receipts are summarized and disclosed
behind a collapsed inspection detail; any non-available receipt remains immediately visible. The
UI never performs arbitrary graph traversal. It resolves labels only against records already
present in the bounded snapshot and keeps stable IDs visible as secondary receipts.

## Read and authority contract

Canvas calls the existing authenticated GET seam with the pinned supported projection version:

```text
GET /product/landscape?projection_version=ace.living-product-projection.g1.v1
```

The client supplies no product selector or scope override; the signed token remains the only
product-scope authority. The development proxy adds `/product` as a same-origin kernel GET path.
There is no new POST, PUT, PATCH, DELETE, WebSocket, tool invocation, extension route, or model
route.

The page exposes only one active recovery control: **Retry read**. It repeats the GET after a
transport failure and explicitly states that no state changed. All other content is static
inspection. The response authority fields remain source-of-truth; the UI's read-only label does
not grant or simulate authority.

## State and failure behavior

| Condition | Visible behavior | Forbidden interpretation |
|---|---|---|
| Loading | “Reading the product map…” | No optimistic or fixture truth |
| Complete | Status receipt plus source receipts | Completeness beyond the bounded contract |
| Partial/degraded/unknown | Prominent banner and attention section | Missing records treated as empty product truth |
| Contested assertion | Disputed lane with contradiction count | Current operational relationship |
| Rejected assertion | Ruled-out lane | Deleted history or accepted truth |
| Missing family | Explicit snapshot-scoped empty state | Claim that the underlying product has none |
| Source unavailable | Source status, reason, record count, bound, and projection issue recovery | Silent omission |
| GET/auth/server failure | Non-mutating error state and GET retry | Background repair or action dispatch |
| Unsupported projection | Existing G1 structured failure through the GET seam | Version fallback without disclosure |

## Verification

Local candidate verification from the isolated IA-R1 worktree currently records:

| Gate | Candidate result |
|---|---|
| Focused API and product-map projection/render/failure tests | **9 passed** |
| Canvas TypeScript and production build | **passed** |
| Full Canvas suite and design enforcement | **288 passed** across 32 files |
| Visual desktop and 390 px mobile inspection against the committed G1 fixture | **passed**; no horizontal overflow, current/disputed lanes remain distinct |
| Full Python non-E2E suite | **6,343 passed, 46 skipped, 234 deselected** |
| Zero-extension non-E2E suite | **6,335 passed, 47 skipped, 241 deselected** |
| Explicit kernel boundary | **4 passed** |
| Ruff lint and formatting | **passed**; 1,770 files formatted |
| Diff whitespace and changed-file secret checks | **passed** |
| Branch, final-head, and merged-main CI | pending |

The focused tests prove the pinned authenticated GET, signed product scope, operator question
hierarchy, distinct operational/contested/rejected lanes, correction and outcome placement,
degraded-source disclosure, stable receipt visibility, and GET-only retry behavior.

The first sandboxed full-suite attempt produced four loopback permission failures and one false G1
replay failure because the original checkout's dirty editable install shadowed the isolated
worktree inside a verifier subprocess. The authoritative rerun used the isolated worktree first on
`PYTHONPATH` and allowed loopback binds; all 6,343 tests passed. No code was changed to bypass a
gate.

## Compatibility and limits

- Canvas and Atrium remain repository-beta research surfaces and are not included in the Python
  wheel or sdist. IA-R1 does not promote them into the 0.1.x package compatibility contract.
- The G1 JSON schema and projection version remain the data authority. The TypeScript interface is
  a consumer declaration, not a second protocol.
- The page is product-scoped and snapshot-based. It is not arbitrary-depth graph navigation,
  cross-product search, pagination, live subscription, editing, or repair.
- The layout groups records for operator orientation; it does not infer causality, rank importance,
  assess truth, or generate a narrative.
- Stable IDs are inspectable, but the first slice does not add record-specific deep-link routes.
- Source quality and assertion confidence are displayed when present. Their absence stays absent;
  the client does not synthesize a score.
- R4 provides a reproducible developer-proxy journey, not independent human usability proof. IA-R1
  likewise requires honest visual and interaction verification before roadmap closeout.

## Reconciliation rule

Implementation alone leaves IA-R1 as a candidate. It may move to `passed` only after full local
verification, visual inspection, green branch CI, versioned roadmap reconciliation, green
final-head CI, merge, and green main CI. A failed gate reopens the outcome; it is not waived by this
document. I1 remains separately scoped and receives no approval-receipt or execution authority from
IA-R1.
