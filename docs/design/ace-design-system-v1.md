# ACE design system v1

## Product thesis

ACE is an Intelligence Operating System. Its interface should make one current,
evidence-backed picture feel calm enough to trust and precise enough to act on.
The system belongs to ACE itself; a public Domain Pack changes vocabulary, sources,
and decision policy, not the product's identity.

The ACE mark is the brand source. It moves from cyan through blue to violet, but the
application deliberately chooses one dominant color: **ACE cognitive blue**. Cyan is
reserved for live evidence, violet is reserved for rare composition/agent-memory
moments, and green returns to its literal semantic role: verified success.

## Reference lock

Research was synthesized from:

- **Primary — Linear Changelog:** midnight command-center density, restrained type,
  graphite borders, and surface layering instead of decorative shadows.
- **Borrowed — Warp:** a disciplined electric-blue focus treatment that highlights
  active product state without tinting the whole interface.
- **Borrowed — Parallel:** evidence-forward research hierarchy and a clear separation
  between a synthesized answer and its source record.

Preserve: cool near-black surfaces, compact Inter/Spline-style typography, 8–12px
radii, thin borders, evidence one interaction away, and one dominant accent.

Reject: HPE green as the Core identity, Vercel-branded blue language, rainbow category
chrome, giant KPI walls, decorative glow, glassmorphism, and gradients outside the
ACE mark or a rare brand transition.

## Color roles

| Role | Light | Dark / Atrium | Meaning |
|---|---:|---:|---|
| ACE cognitive blue | `#315DDE` | `#7597FF` | Primary actions, selected intelligence, links, focus, ACE identity |
| Spectral cyan | `#0F8294` | `#55D6E6` | Live/in-motion evidence only |
| Success green | `#178A4B` | `#48C77A` | Verified, completed, or accepted state only |
| Canvas | `#FFFFFF` | `#070A10` | Working surface / Atrium command center |
| Card | `#FFFFFF` | `#101620` | Evidence and intelligence records |
| Border | `#E6E8E9` | `#263248` | Structure without decorative elevation |

Blue does not mean “good.” Green does not mean “ACE.” A Domain Pack may add chart or
taxonomy hues, but it must not change these meanings.

## Typography and density

- Spline Sans is the product voice; Spline Sans Mono is used for timestamps, counts,
  identities, receipts, and provenance.
- Product headings use medium/semibold weight and tight tracking, not oversized bold
  marketing typography.
- Spacing follows the existing 4px grid. Atrium stays compact; onboarding may breathe
  more, but it should still feel like the same operating system.

## Surfaces and interaction

- Use borders and small tonal steps for depth. Avoid a stack of large shadows.
- Cards use 8–12px radius; pills are reserved for status and short filters.
- Blue appears on the active navigation item, focus ring, primary action, intelligence
  lineage, and key identity moments.
- Every synthesized claim should be one interaction from evidence and provenance.
- Motion communicates a state change. It never decorates an otherwise static card.

## Domain and deployment boundary

Core ships the ACE base theme and owns its tokens, accessibility, primitives, and
Atrium composition. Public Domain Packs inherit the ACE theme and contribute only
domain vocabulary, data visualization needs, and semantic policy.

Customer-specific branding is a deployment overlay. For example, an HPE deployment
may install an HPE theme privately, but the public Market Intelligence pack must not
make HPE green, fonts, or product naming its default.

## Opportunity product language

An Opportunity is intelligence awaiting a decision: a favorable or avoidable opening
supported by a Signal, a material Shift, and enough evidence to form a bounded Case.
It is not a lead, task, or autonomous action. See
[Atrium opportunity contract v1](atrium-opportunity-contract-v1.md).
