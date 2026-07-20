"""Registry — the single facade an extension talks to.

An extension wires all its capabilities through this object; it never imports kernel
internals directly. That makes `Registry` the *stable extension contract* — the
"syscall layer" extensions build against.

Instruments delegate to the pre-existing `engine.cognition.instrument_registry`
(which already had a `register_instrument` seam). The other capabilities
accumulate in module-level stores with read accessors; the kernel consumes those
per-capability as each is wired in (recipe loader, MCP server, committee
resolution, schema migrate). Keeping them here means the contract is whole even
while the consume-side integration lands incrementally.
"""

from __future__ import annotations

from typing import Any, Callable

# Extension-contributed stores the kernel reads from (instruments are the exception —
# they go straight to the existing instrument registry).
_recipes: dict[str, Any] = {}
# Routing: which extension recipe a classification selects. The generic composer
# merges these so its discipline/task_type maps stay free of extension names.
_recipe_disciplines: dict[str, str] = {}  # discipline -> recipe name
_recipe_task_types: dict[str, str] = {}  # task_type -> recipe name
_committees: dict[str, Callable[..., Any]] = {}
_personas: list[Any] = []
_frameworks: list[Any] = []
_tools: list[dict[str, Any]] = []  # {"fn": callable, "title": str}
_schema_paths: list[str] = []
# Briefing-section providers: async (db) -> {available, markdown, metrics}. The
# sentinel briefing loops these so extensions can contribute sections to the report.
_briefing_sections: list[dict[str, Any]] = []  # {"builder": async fn, "metrics_key": str, "timeout": float}
# Verify-time checks a MAKE arm runs in verify(). fn(files:[{path,content}]) -> [violation];
# violation = {rule, severity ('enforced'|'advisory'), file, line, snippet}. Enforced ones
# fail the build closed; advisory ones only surface. Kept generic — no policy names here.
_verify_checks: list[Callable[[list[dict]], list[dict]]] = []


class Registry:
    """The extension facade. An extension's ``register(reg)`` calls these methods."""

    def register_instrument(self, slug: str, module_path: str) -> None:
        """Register an LLM pipeline instrument (module exposing ``run(**kwargs)``)."""
        # Lazy import: avoid pulling the heavy cognition chain at extension-module
        # import time, and avoid an import cycle.
        from core.engine.cognition.instrument_registry import register_instrument

        register_instrument(slug, module_path)

    def register_recipe(
        self,
        name: str,
        recipe: Any,
        *,
        disciplines: list[str] | None = None,
        task_types: list[str] | None = None,
    ) -> None:
        """Register a recipe and, optionally, the classifications that should
        select it.

        ``recipe`` may be either a module path string (the original convention,
        recipe modules expose ``get_meta_skill()``) or a ``MetaSkill`` object
        directly (used by the YAML loader). The composer's ``_load_recipe()``
        handles both.

        Raises RuntimeError if ``name`` is already registered — silent overwrite
        masks real bugs (two extensions fighting over a slug).
        """
        if name in _recipes:
            raise RuntimeError(f"Recipe '{name}' already registered (existing: {_recipes[name]!r})")
        _recipes[name] = recipe
        for d in disciplines or []:
            _recipe_disciplines[d] = name
        for t in task_types or []:
            _recipe_task_types[t] = name

    def register_committee(self, name: str, builder: Callable[..., Any]) -> None:
        _committees[name] = builder

    def register_personas(self, personas: list[Any]) -> None:
        _personas.extend(personas)

    def register_frameworks(self, frameworks: list[Any]) -> None:
        _frameworks.extend(frameworks)

    def register_tool(self, fn: Callable[..., Any], *, title: str | None = None) -> None:
        _tools.append({"fn": fn, "title": title or getattr(fn, "__name__", "tool")})

    def register_verify_check(self, fn: Callable[[list[dict]], list[dict]]) -> None:
        """Register a verify-time check (see `_verify_checks`). MAKE arms run every
        registered check in verify() and fail closed on enforced violations."""
        _verify_checks.append(fn)

    def register_sentinel(
        self,
        name: str,
        *,
        cron: str,
        description: str,
        fn: Callable[..., Any],
        trigger: Callable[[str], Any] | None = None,
    ) -> None:
        """Register a 24/7 sentinel engine the kernel scheduler runs on a cron.

        ``fn`` is ``async def (product_id: str) -> dict``. Delegates to the
        kernel's sentinel engine registry (the same store kernel engines use),
        so extension sentinels appear in ``list_engines()``, honor per-product
        schedule overrides, and emit the same metrics. Re-registering the same
        ``fn`` under the same ``name`` is idempotent (a no-op); registering a
        different ``fn`` under an existing ``name`` raises ValueError — silent
        overwrite masks real bugs.
        """
        # Lazy import: mirrors register_instrument — avoid pulling the sentinel
        # chain at extension-module import time, and avoid an import cycle.
        from core.engine.sentinel.registry import register_engine

        register_engine(name, cron, description, trigger=trigger)(fn)

    def register_schema(self, surql_path: str) -> None:
        _schema_paths.append(surql_path)

    def register_briefing_section(
        self,
        builder: Callable[..., Any],
        *,
        metrics_key: str,
        timeout: float = 10.0,
    ) -> None:
        """Register a daily-briefing section provider.

        ``builder`` is ``async def (db) -> dict`` returning
        ``{available: bool, markdown: str, metrics: dict}``. The sentinel briefing
        appends ``markdown`` when available and records ``metrics`` under
        ``metrics_key``. ``timeout`` bounds the section so a slow extension can't
        stall the whole briefing.
        """
        _briefing_sections.append({"builder": builder, "metrics_key": metrics_key, "timeout": timeout})


# ---- read-side accessors (kernel consumes these as each capability is wired) ----
# Each accessor ensures extensions are loaded first, so a consume-side reader never
# sees an empty store just because no one triggered discovery yet. Lazy import of
# the loader avoids the loader<->registry import cycle.
def _ensure_extensions_loaded() -> None:
    from core.engine.extensions.loader import ensure_loaded

    ensure_loaded()


def registered_recipes() -> dict[str, Any]:
    _ensure_extensions_loaded()
    return dict(_recipes)


def registered_recipe_disciplines() -> dict[str, str]:
    _ensure_extensions_loaded()
    return dict(_recipe_disciplines)


def registered_recipe_task_types() -> dict[str, str]:
    _ensure_extensions_loaded()
    return dict(_recipe_task_types)


def registered_committees() -> dict[str, Callable[..., Any]]:
    _ensure_extensions_loaded()
    return dict(_committees)


def registered_personas() -> list[Any]:
    _ensure_extensions_loaded()
    return list(_personas)


def registered_frameworks() -> list[Any]:
    _ensure_extensions_loaded()
    return list(_frameworks)


def registered_tools() -> list[dict[str, Any]]:
    _ensure_extensions_loaded()
    return list(_tools)


def registered_schema_paths() -> list[str]:
    _ensure_extensions_loaded()
    return list(_schema_paths)


def registered_briefing_sections() -> list[dict[str, Any]]:
    _ensure_extensions_loaded()
    return list(_briefing_sections)


def registered_verify_checks() -> list[Callable[[list[dict]], list[dict]]]:
    _ensure_extensions_loaded()
    return list(_verify_checks)
