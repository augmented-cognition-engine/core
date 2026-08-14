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

- **Foundation — [Linear Changelog](https://styles.refero.design/style/11d3e58a-87d7-4a9a-bbf5-720f4fd3ffc6):**
  near-black precision surfaces, quiet white/gray typography, compact density,
  hairline geometry, and confident hierarchy without ornamental UI.
- **Hierarchy — [Attio](https://styles.refero.design/style/9f0c028b-6b11-415e-ab92-f32e4597cbe2):**
  an editorial difference between the operating headline and the supporting system
  chrome. Atrium translates this through the existing Spline family rather than
  importing Attio's type identity.
- **Atmosphere — [Origin Financial](https://styles.refero.design/style/466f6aa2-a9f6-4dcd-9626-73806a01d00e):**
  a contained data glow that makes one focal picture feel alive without tinting the
  whole application.
- **Interaction — [Raycast](https://styles.refero.design/style/3b6a17f0-3bdf-418c-a95e-0b89e5a8b2f8):**
  neutral action surfaces and disciplined accent rationing. Its accent hue is not
  borrowed; Atrium's color comes from the ACE mark.

Color is locked to representative opaque clusters measured from the authoritative
4096px ACE mark: spectral cyan `#58E8F9`, evidence blue `#2896E7`, and identity
violet `#9777F5`. Reference products may influence composition, never ACE color.

Preserve: achromatic near-black surfaces, compact Spline typography, 8–12px radii,
thin borders, evidence one interaction away, and one controlled ACE-mark accent.

Reject: blue-tinted surface ladders, importing a reference product's accent color, HPE
green as the Core identity, rainbow category chrome, giant KPI walls, ambient glow on
generic cards, glassmorphism, and decorative gradients outside a bounded ACE-spectrum
intelligence visualization.

## Signature composition

Atrium's signature is the **Intelligence Horizon**. Admitted sources and detected
movement converge into one immutable, cited Brief; the same picture then opens toward
grounded investigation and a human decision. The visualization uses actual resource
counts and provenance links, never invented confidence or activity metrics. A contained
cyan → evidence-blue → violet field echoes the ACE mark while the surrounding shell
stays achromatic.

The Opportunities surface uses the paired **Decision Aperture**: Signal → Shift → Case
is rendered as a progression, not three equivalent KPI cards. The last stage is an
opening for human judgment, not an autonomous action. Together these compositions make
the product legible as an Intelligence OS rather than a collection of dashboards.

Within every intelligence record, narrative weight is intentionally asymmetric:

1. **What changed** is the lead claim and receives the strongest type and spacing.
2. **Why it matters** is the interpretation and appears as a secondary annotation.
3. **Evidence and timing** form a compact receipt beneath or beside the narrative.

Compact cards omit the repeated four-part grid entirely: they show the change, a short
“Why” annotation when available, and the existing provenance/time receipt. Full detail
remains one interaction away in the resource sheet.

## Color roles

| Role | Light | Dark / Atrium | Meaning |
|---|---:|---:|---|
| Primary action | `#315DDE` | `#E7E5E1` | Atrium uses a light neutral fill rather than a chromatic block |
| Focus / identity | `#315DDE` | `#9777F5` | Spectral violet from the ACE mark for selection, links, focus, and ACE voice |
| Spectral cyan | `#0F8294` | `#58E8F9` | Live/in-motion evidence only |
| Evidence blue | `#315DDE` | `#2896E7` | Information, evidence, and data visualization only |
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
- Operating-picture headlines may use a large, light-to-medium editorial scale. Product
  chrome and record titles remain compact; oversized bold marketing typography is not
  used inside the working system.
- Spacing follows the existing 4px grid. Atrium stays compact; onboarding may breathe
  more, but it should still feel like the same operating system.

## Surfaces and interaction

- Use borders and small tonal steps for most depth. One focal Intelligence Horizon or
  Decision Aperture may carry a broad, low-opacity shadow to separate the operating
  picture from the shell; generic cards may not.
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
