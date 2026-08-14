# ACE design system v1

## Product thesis

ACE is an Intelligence Operating System. Its interface should make one current,
evidence-backed picture feel calm enough to trust and precise enough to act on.
The system belongs to ACE itself; a public Domain Pack changes vocabulary, sources,
and decision policy, not the product's identity.

The ACE mark is the color source, moving from cyan through blue to violet. The product
chrome is quieter than the mark: **Atrium is neutral-first**, with the mark's spectral
violet used as sparse focus punctuation rather than washing the command center in blue.
Blue remains available for informational and evidence semantics, cyan is reserved for
live intelligence, violet identifies ACE selection and voice, and green keeps its
literal semantic role: verified success.

## Reference lock

Research was synthesized through Refero from:

- **Primary — [Linear](https://styles.refero.design/style/90ce5883-bb24-4466-93f7-801cd617b0d1):**
  near-black precision surfaces, quiet white/gray typography, compact density, and
  hairline geometry instead of decorative shadows.
- **Supporting — [Raycast](https://styles.refero.design/style/3b6a17f0-3bdf-418c-a95e-0b89e5a8b2f8):**
  a 98%-achromatic dark cockpit, neutral action surfaces, and disciplined accent
  rationing. Its accent hue is not borrowed; Atrium's color comes from the ACE mark.
- **Borrowed — Parallel:** evidence-forward research hierarchy and a clear separation
  between a synthesized answer and its source record.

Preserve: achromatic near-black surfaces, compact Spline typography, 8–12px radii,
thin borders, evidence one interaction away, and one controlled ACE-mark accent.

Reject: blue-tinted surface ladders, importing a reference product's accent color, HPE
green as the Core identity, rainbow category chrome, giant KPI walls, decorative glow,
glassmorphism, and gradients outside the ACE mark or a rare brand transition.

## Color roles

| Role | Light | Dark / Atrium | Meaning |
|---|---:|---:|---|
| Primary action | `#315DDE` | `#E7E5E1` | Atrium uses a light neutral fill rather than a chromatic block |
| Focus / identity | `#315DDE` | `#9B7BF6` | Spectral violet from the ACE mark for selection, links, focus, and ACE voice |
| Spectral cyan | `#0F8294` | `#62C3BE` | Live/in-motion evidence only |
| Success green | `#178A4B` | `#4CC984` | Verified, completed, or accepted state only |
| Canvas | `#FFFFFF` | `#08090A` | Working surface / Atrium command center |
| Card | `#FFFFFF` | `#111214` | Evidence and intelligence records |
| Border | `#E6E8E9` | `#2A2B2D` | Structure without decorative elevation |

Violet identifies ACE; it does not mean “good.” Green remains literal success. Blue is
not forbidden; it is removed from generic Atrium chrome and reserved for information,
evidence, or data visualization. A Domain Pack may add chart or taxonomy hues, but it
must not change these meanings.

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
- Atrium uses neutral primary actions; spectral violet appears on active navigation,
  focus rings, links, and small ACE-voice moments. Large panels remain achromatic.
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
