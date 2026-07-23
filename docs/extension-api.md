# ACE Extension API — stability contract

**Applies to:** the `ace.extensions` plugin layer (`core/engine/extensions/`).
**Versioning:** the extension API version IS the kernel version (SemVer).
Breaking changes to any **Stable** surface happen only on a kernel MAJOR
release, with migration notes in the changelog. **Experimental** surfaces may
change on MINOR releases.

## Stable

| Surface | Contract |
|---|---|
| Entry-point group `ace.extensions` | Permanent. `name = "pkg.module:ExtensionClass"` per extension. |
| `Extension` protocol | `name: str`, `version: str`, `register(reg: Registry) -> None`. |
| `Registry.register_instrument(slug, module_path)` | Contribute an instrument. |
| `Registry.register_recipe(...)` | Contribute a recipe + its discipline/task-type routing. |
| `Registry.register_committee(name, builder)` | Contribute a committee builder. |
| `Registry.register_personas(personas)` | Contribute personas. |
| `Registry.register_frameworks(frameworks)` | Contribute frameworks. |
| `Registry.register_tool(fn, *, title=None)` | Contribute an MCP tool. |
| `Registry.register_schema(surql_path)` | Contribute a SurrealQL schema the extension migrator applies. |
| `load_extensions()` semantics | Idempotent; a broken extension is logged and skipped, never fatal. |
| `ACE_DISABLE_EXTENSIONS=1` | Kill switch: boot the naked kernel (process-lifetime). |

Exact signatures live in `core/engine/extensions/registry.py` — the table
names the commitment; the source names the types.

## Experimental

- `Registry.register_task_action(...)` — register extension-owned structured
  context preparation and optional outcome projection on Core's durable task
  lifecycle. The public wire contracts are `extension-invocation-v1` and
  `extension-invocation-receipt-v1`; interrupted execution resumes as a linked
  successor attempt, never a fictitious continuation of a lost provider stream.
  See the [experimental invocation contract](extension-invocation-contract.md) for wire fields,
  authority, failure behavior, restart evidence, and limitations.
- `Registry.register_sentinel(...)` — sentinel engine contribution.
- `Registry.register_briefing_section(...)` — briefing composition hooks.
- Canvas extension wiring (`core/ui/canvas/src/app/ext/`).
- `ACE_EXTENSIONS` dev-list loading (unpackaged local extensions).

## What belongs in an extension

Would it be useless to a different domain? Then it is extension config, not
kernel. The dependency direction is one-way — extensions import `core`;
`core` never imports extensions (enforced by `tests/test_kernel_boundary.py`).

For task actions, that rule means Core owns authentication, product/user scope,
workspace-claim enforcement, contract negotiation, idempotency, task persistence,
provider execution, attempt lineage, cancellation state, and receipt normalization.
The extension owns reference resolution, domain authorization, prompt preparation,
artifact creation, and domain outcome projection. A resolver must report each
reference as `resolved`, `declared`, `missing`, or `rejected`; carrying an
identifier into a prompt is not reported as retrieval. `resolved` requires matching
private context content plus immutable version, hash, resolver, and product-scope
evidence. Projected recommendations remain separate from human decisions and later
adoption.

The experimental capability manifest negotiates accepted input versions, one output
version, lifecycle operations, cancellation support, resolver/artifact capabilities,
required authorities, and feature flags. Discovery is deterministic, bounded to 200
actions, and rejects duplicate registrations. Machine-readable schemas are available
from authenticated `GET /extension-invocations/schemas`.

## Starting point

Run `python -m scripts.scaffold_extension <your_domain>` (see
[Build your first extension](build-your-first-extension.md)) — it copies the
shipped reference extension (`extensions/reference/`), so the template can
never drift from the worked example.
