# extensions/

Vertical specializations on top of ACE core. **Extensions are how ACE
reaches specific markets** — they inherit the engine + design system,
override what they need (theme, copy, scope, committee composition),
and ship as scoped products.

## Current extensions

- **`extensions/reference/`** — the canonical worked example a
  contributor copies to start their own domain extension. Demonstrates
  every extension point the kernel consumes (extension registration,
  recipes, committees, instruments). Registered as the `product`
  extension via the `ace.extensions` entry point in `pyproject.toml`.
- **Private extensions** — domain-specific products built on the same
  contract, living in their own repos outside this tree and owned by
  their maintainers. The contract is identical to the reference
  extension's; "private" is just repo visibility.

## The contract every extension follows

An extension is the combination of:

1. **A Python package** that registers with the engine via an extension
   entry point in `pyproject.toml` (e.g.
   `product = "extensions.reference.extension:ProductExtension"`).
   Provides:
   - Domain-specific recipes (`recipes/`)
   - Committee composition (which archetypes are in the room)
   - Domain vocabulary (schema extensions, instrument tools)
   - MCP tools the extension exposes
2. **A UI surface** at `ui/` — the extension's product UI (static
   HTML now, React later).
3. **A theme** at `ui/theme/` — design-system overrides (CSS files
   that retune primitives + components for this extension) plus
   `ui/theme/branding/` for logos and brand assets. The corresponding
   TypeScript theme for the React canvas lives at
   `core/ui/canvas/src/design/themes/<name>.ts` and gets retired into
   `ui/theme/` once the extension has its own React port.
4. **A narrative scope** — what does the extension *do*? Who is its
   user? What does success look like? A README per extension.

## Extension template

```
extensions/<name>/
├── README.md           ← what this extension is, who it serves
├── <package>/          ← Python: instruments, schema, queries
├── recipes/            ← reasoning recipes
├── tests/              ← extension tests
├── <name>_extension.py ← extension entry point class
├── ui/                 ← the extension's UI (static HTML for now)
│   ├── *.html
│   └── theme/          ← design-system overrides for the static UI
│       ├── *.css       ← (color, components, dimension, primitives, ...)
│       ├── theme.css   ← master theme entry
│       └── branding/   ← logos, brand assets
└── pyproject.toml      ← (if shipped independently)
```

## How to build an extension

(Start by copying `extensions/reference/` — it is the canonical
scaffold and demonstrates every kernel extension point.)

1. Decide the vertical — who you're serving and what reasoning task
   you're scoping ACE to.
2. Compose the committee — which archetypes weigh in?
   (See `core/ui/canvas/src/design/disciplineIdentity.ts` for the
   palette of 14 archetypes; pick 3–6.)
3. Build the Python package with recipes + instruments + schema.
4. Build the UI surface in `ui/` (start with static HTML, port to React
   when stable). Drop design-system overrides into `ui/theme/`.
5. Add the TypeScript theme at
   `core/ui/canvas/src/design/themes/<name>.ts` if you want the canvas
   to retint when your extension is active.
6. Curate the narrative — what fills the canvas when the user opens
   the extension? What's the brief-me-back card? What does the
   reconciliation feel like at +30d?

## What extensions are NOT

- Not "branded variants" — they're scoped products with their own
  scope, vocabulary, and committee. The visual theme is one layer of
  many.
- Not "modes" — modes were the old ShellNav abstraction (pulse, atc,
  map, intel, foresight) where each was a destination. Extensions are
  products, not views.
- The plugin layer is named `extensions` end-to-end: the module is
  `core/engine/extensions/`, the contract is `Extension`, and packages
  declare an `ace.extensions` entry point.

## How `extensions/` relates to the rest of the repo

```
ace/
├── core/
│   ├── engine/      ← Python reasoning OS — what gets installed
│   ├── schema/      ← knowledge-graph schemas
│   ├── mcp/         ← MCP server
│   └── ui/canvas/   ← React reference UI — what gets shipped
└── extensions/      ← vertical specializations (this directory's role)
    └── reference/   ← canonical worked example
```

Each extension owns its own demos, branding, and narrative artifacts —
there's no separate top-level `references/` directory.
