# 0.9.0 Single-user Intelligence Builder work packet

## Outcome

One person can install ACE and one public Domain Pack, launch Atrium, choose what they want to
understand, connect authorized sources, review ACE's proposed model and watches, receive a cited
first Brief, and keep that intelligence current without learning Core, Intelligence, pack, or
connector internals.

The signature journey is:

```text
install → choose intelligence → describe the goal → connect sources
→ review concept model → review watches → first cited Brief
→ later source change → decision-readable update → Ask ACE → feedback → restart/reopen
```

## Product contract

The journey is for one local operator. It must feel like one product even though the implementation
retains the Core + Intelligence + Domain Pack + connector boundaries.

### Required experience

1. **Install and launch.** One documented supported path installs public artifacts and opens Atrium.
2. **Choose.** Atrium discovers installed World and Market profiles and always offers Custom
   Intelligence without hard-coding either domain into Core.
3. **Describe.** The operator chooses an outcome or writes the bounded question they need to stay
   ahead of.
4. **Connect.** ACE explains each source, requested scope, access mode, and expected contribution
   before any read is authorized. Credentials remain host-owned.
5. **Map.** The Mapping Agent proposes editable entities, relationships, terminology, aliases, and
   exclusions with exact source references.
6. **Watch.** The Monitoring Agent proposes material changes, thresholds, cadence, urgency, and
   delivery posture. Silence remains valid.
7. **Brief.** The Briefing Agent creates a useful first Brief showing what changed or currently
   matters, why, how the conclusion was derived, when the evidence applies, uncertainty, conflicts,
   unknowns, and citations.
8. **Continue.** A later source change becomes an append-only update. Atrium exposes Signals,
   Shifts, Opportunities, Briefs, monitors, and exact revision differences.
9. **Ask and correct.** Ask ACE answers from authorized intelligence rather than generic chat.
   Feedback records what was useful, wrong, missing, or irrelevant and may propose—but never
   silently activate—changed relevance policy.
10. **Own.** Restart/reopen, export, deletion, backup, and restore preserve or remove the exact
    supported personal state as documented.

## Release slices

| Slice | Required result | Primary owner |
|---|---|---|
| U1 — roadmap and contract | Single-user 0.9/1.0 promises, boundaries, issues, and acceptance matrix agree | Core |
| U2 — Atrium golden path | Catalog selection starts one resumable real onboarding session with clear progress and failure states | Core application + Atrium |
| U3 — source composition | World AI and Market sources expose honest access, credential, health, and contribution states | Domain products + separate connectors |
| U4 — first value | Approved onboarding material produces a decision-readable cited first Brief and later append-only update | Core application + Intelligence |
| U5 — grounded use | Ask ACE and feedback use the same authorized resources and preserve exact context/use receipts | Core application + Atrium |
| U6 — personal ownership | Restart/reopen, export, deletion, backup, and restore pass for the supported local topology | Core |
| U7 — release proof | Clean public install, upgrade, accessibility, security, schema, package, two-domain, and demo gates pass | Core + World + Market |

## Acceptance matrix

| Gate | Must prove | Must fail closed |
|---|---|---|
| Clean install | Public packages only; no source checkout or private package required | missing/incompatible package |
| Catalog | Installed profiles plus generic Custom path; no domain code in Core | malformed or duplicate profile |
| Connection | Exact source scope and permission visible before read | stale proposal, missing grant, credential leak |
| Model and watch | Exact approved proposal material is persisted and resumable | unapproved or changed proposal |
| First Brief | Material current state, disagreement/unknowns, why/how/when, and claim-level citations | uncited material claim, empty evidence, hidden prepared/live mix |
| Continuous update | Later evidence creates a new attributable revision and semantic diff | history rewrite, future leakage, duplicate-origin inflation |
| Ask ACE | Answer cites authorized current intelligence and exposes limits | unauthorized retrieval, generic unsupported answer |
| Feedback | Correction is attributable and policy change remains proposal-only | silent reweighting or authority widening |
| Ownership | restart/reopen, export, deletion, backup, and restore behave as documented | partial restore presented as complete; deleted data reappears |
| Domain neutrality | World and Market reproduce the journey through unchanged public interfaces | domain noun or branch in Core/Intelligence |

## Signature demonstrations

### World Intelligence — AI Command Center

Use multiple attributable AI source families to explain one material change across research,
models, economics, infrastructure, policy, security, companies, markets, or open-source adoption.
The visual update must answer what changed, why it matters, how ACE knows, when it happened, what
could change the conclusion, and which sources independently support it.

### Market Intelligence

Use public market evidence to explain one competitive, product, market, customer, performance, or
narrative change. The experience is an intelligence command center for marketers, not a content
creation system; Jasper, Workfront, publishing, and other downstream tools remain downstream.

## Explicitly after 1.0

- organizations, teams, invitations, and tenant isolation;
- shared workspaces and multiplayer approvals;
- delegated administration and complex organizational roles;
- managed hosting and marketplace operation;
- hostile-extension sandboxing and distributed execution; and
- enterprise-scale operational guarantees beyond the documented local topology.

These are valuable expansions. They are not prerequisites for a complete first release that works
for one person.
