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

import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable

from core.engine.extensions.invocation import (
    PrepareTaskAction,
    ProjectOutcome,
    RegisteredTaskAction,
    ValidateOutcome,
)

# Extension-contributed stores the kernel reads from (instruments are the exception —
# they go straight to the existing instrument registry).
_recipes: dict[str, Any] = {}
_recipe_metadata: dict[str, "RegisteredRecipeSource"] = {}
# Routing: which extension recipe a classification selects. The generic composer
# merges these so its discipline/task_type maps stay free of extension names.
_recipe_disciplines: dict[str, str] = {}  # discipline -> recipe name
_recipe_task_types: dict[str, str] = {}  # task_type -> recipe name
_committees: dict[str, Callable[..., Any]] = {}
_personas: list[Any] = []
_frameworks: list[Any] = []
_tools: list[dict[str, Any]] = []  # {"fn": callable, "title": str}
_schema_paths: list[str] = []
_unsupported_registrations: list["UnsupportedRegistration"] = []
# Briefing-section providers: async (db) -> {available, markdown, metrics}. The
# sentinel briefing loops these so extensions can contribute sections to the report.
_briefing_sections: list[dict[str, Any]] = []  # {"builder": async fn, "metrics_key": str, "timeout": float}
# Verify-time checks a MAKE arm runs in verify(). fn(files:[{path,content}]) -> [violation];
# violation = {rule, severity ('enforced'|'advisory'), file, line, snippet}. Enforced ones
# fail the build closed; advisory ones only surface. Kept generic — no policy names here.
_verify_checks: list[Callable[[list[dict]], list[dict]]] = []
# Extension-owned task preparation and outcome projection. Core owns the
# invocation lifecycle; these callables are the domain resolution boundary.
MAX_TASK_ACTIONS = 200
MAX_COGNITION_RECIPES = 64
MAX_COGNITION_ROUTES = 256
MAX_COGNITION_RESOURCES = 64
MAX_COGNITION_DECLARATIONS = 64
MAX_COGNITION_CONTRACT_VERSIONS = 8
CURRENT_COGNITION_CONTRACT = "ace.cognition.revision/v1"
LEGACY_COGNITION_REGISTRATION = "legacy-recipe-registration/v1"
TaskActionIdentity = tuple[str, str]
_task_actions: dict[TaskActionIdentity, RegisteredTaskAction] = {}
# Provider-neutral grounded-state ingestion adapters.  Adapters only map
# source-specific extraction into Core contracts; Core owns product scope,
# identity, lifecycle, persistence, and receipts.
GroundedStateAdapterIdentity = tuple[str, str]
_grounded_state_adapters: dict[GroundedStateAdapterIdentity, Any] = {}
MAX_GROUNDED_STATE_ADAPTERS = 50
_ADAPTER_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")
_COGNITION_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_COGNITION_DECLARATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$")
_RESOURCE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _bounded_declarations(values: list[str] | None, *, field: str) -> tuple[str, ...]:
    raw = [] if values is None else values
    if (
        not isinstance(raw, list)
        or len(raw) > MAX_COGNITION_DECLARATIONS
        or any(not isinstance(item, str) or not _COGNITION_DECLARATION.fullmatch(item) for item in raw)
    ):
        raise ValueError(f"invalid_cognition_{field}")
    return tuple(sorted(set(raw)))


def _validated_resource_manifest(resource_manifest: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    resources = {} if resource_manifest is None else resource_manifest
    if not isinstance(resources, dict) or len(resources) > MAX_COGNITION_RESOURCES:
        raise ValueError("invalid_cognition_resource_manifest")
    validated: list[tuple[str, str]] = []
    for resource, raw_digest in resources.items():
        if not isinstance(resource, str) or not isinstance(raw_digest, str):
            raise ValueError("invalid_cognition_resource_manifest")
        digest = raw_digest.lower()
        posix_path = PurePosixPath(resource)
        windows_path = PureWindowsPath(resource)
        raw_parts = resource.replace("\\", "/").split("/")
        if (
            not _RESOURCE_PATH.fullmatch(resource)
            or "\\" in resource
            or posix_path.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or posix_path.as_posix() != resource
            or any(part in {"", ".", ".."} for part in raw_parts)
            or not _SHA256.fullmatch(digest)
        ):
            raise ValueError("invalid_cognition_resource_manifest")
        validated.append((resource, digest))
    return tuple(sorted(validated))


@dataclass(frozen=True)
class RegisteredRecipeSource:
    """Extension provenance retained alongside the legacy recipe facade."""

    name: str
    recipe: Any
    extension_id: str
    extension_version: str
    disciplines: tuple[str, ...]
    task_types: tuple[str, ...]
    cognition_contract_version: str
    accepted_core_contract_versions: tuple[str, ...]
    package_digest: str
    resource_manifest: tuple[tuple[str, str], ...]
    required_authorities: tuple[str, ...]
    side_effects: tuple[str, ...]
    trusted_in_process: bool
    compatibility: str

    def public_manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "extension_id": self.extension_id,
            "extension_version": self.extension_version,
            "cognition_contract_version": self.cognition_contract_version,
            "accepted_core_contract_versions": list(self.accepted_core_contract_versions),
            "package_digest": self.package_digest,
            "resource_manifest": [
                {"resource": resource, "sha256": digest} for resource, digest in self.resource_manifest
            ],
            "required_authorities": list(self.required_authorities),
            "side_effects": list(self.side_effects),
            "trusted_in_process": self.trusted_in_process,
            "compatibility": self.compatibility,
            "disciplines": list(self.disciplines),
            "task_types": list(self.task_types),
        }


@dataclass(frozen=True)
class UnsupportedRegistration:
    extension_id: str
    extension_version: str
    capability: str
    stable_key: str
    disposition: str = "unsupported_registration"


@dataclass(frozen=True)
class CognitionContractNegotiation:
    """Pre-registration proof that an extension and Core share a contract."""

    extension_id: str
    extension_version: str
    extension_contract_version: str
    core_contract_version: str
    accepted_core_contract_versions: tuple[str, ...]
    compatibility: str = "current"


def _recipe_digest(recipe: Any) -> str:
    if isinstance(recipe, str):
        try:
            spec = find_spec(recipe)
        except (ImportError, ModuleNotFoundError, ValueError):
            spec = None
        origin = spec.origin if spec is not None else None
        if origin and Path(origin).is_file():
            return sha256(Path(origin).read_bytes()).hexdigest()
        return sha256(recipe.encode("utf-8")).hexdigest()
    try:
        from core.engine.cognition.contracts import canonical_hash

        return canonical_hash(asdict(recipe))
    except Exception as exc:
        raise TypeError("extension recipe must be a module path or dataclass recipe") from exc


class Registry:
    """The extension facade. An extension's ``register(reg)`` calls these methods."""

    def __init__(self, *, extension_id: str | None = None, extension_version: str | None = None) -> None:
        self._extension_id = extension_id
        self._extension_version = extension_version
        self._cognition_negotiation: CognitionContractNegotiation | None = None

    def negotiate_cognition_contract(
        self,
        *,
        extension_contract_version: str,
        accepted_core_contract_versions: list[str] | tuple[str, ...],
    ) -> CognitionContractNegotiation:
        """Fail before registration when package cognition contracts cannot mix.

        Current extensions call this as their first ``register`` operation. An
        N-1 Core has no negotiation method, so a current extension can refuse
        deterministically before mutating any old registry. N-1 extensions do
        not call it; their legacy ``register_recipe`` signature remains an
        explicitly labelled adapter input on current Core.
        """
        if not self._extension_id or not self._extension_version:
            raise RuntimeError("cognition_contract_negotiation_requires_scoped_registry")
        if (
            not isinstance(accepted_core_contract_versions, (list, tuple))
            or not accepted_core_contract_versions
            or len(accepted_core_contract_versions) > MAX_COGNITION_CONTRACT_VERSIONS
            or any(
                not isinstance(item, str) or not _COGNITION_DECLARATION.fullmatch(item)
                for item in accepted_core_contract_versions
            )
        ):
            raise ValueError("invalid_accepted_core_cognition_contracts")
        accepted = tuple(sorted(set(accepted_core_contract_versions)))
        if extension_contract_version != CURRENT_COGNITION_CONTRACT:
            raise RuntimeError("unsupported_cognition_contract_version")
        if CURRENT_COGNITION_CONTRACT not in accepted:
            raise RuntimeError("incompatible_core_cognition_contract")
        receipt = CognitionContractNegotiation(
            extension_id=self._extension_id,
            extension_version=self._extension_version,
            extension_contract_version=extension_contract_version,
            core_contract_version=CURRENT_COGNITION_CONTRACT,
            accepted_core_contract_versions=accepted,
        )
        self._cognition_negotiation = receipt
        return receipt

    def register_instrument(self, slug: str, module_path: str) -> None:
        """Register an LLM pipeline instrument (module exposing ``run(**kwargs)``)."""
        # Lazy import: avoid pulling the heavy cognition chain at extension-module
        # import time, and avoid an import cycle.
        from core.engine.cognition.instrument_registry import register_instrument

        register_instrument(
            slug,
            module_path,
            extension_id=self._extension_id,
            extension_version=self._extension_version,
            contract_version=(
                "ace.cognition.instrument/v1"
                if self._extension_id and self._extension_version
                else "legacy-python-instrument/v1"
            ),
        )

    def register_recipe(
        self,
        name: str,
        recipe: Any,
        *,
        disciplines: list[str] | None = None,
        task_types: list[str] | None = None,
        cognition_contract_version: str = LEGACY_COGNITION_REGISTRATION,
        accepted_core_contract_versions: list[str] | None = None,
        resource_manifest: dict[str, str] | None = None,
        required_authorities: list[str] | None = None,
        side_effects: list[str] | None = None,
        trusted_in_process: bool = True,
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
        if not _COGNITION_KEY.fullmatch(name):
            raise ValueError("extension cognition name must be a bounded stable token")
        if not trusted_in_process:
            raise RuntimeError("untrusted_in_process_extension_code_is_unsupported")
        resources = _validated_resource_manifest(resource_manifest)
        if len(_recipes) >= MAX_COGNITION_RECIPES:
            raise RuntimeError(f"Extension recipe registry is limited to {MAX_COGNITION_RECIPES} entries")
        if cognition_contract_version not in {
            CURRENT_COGNITION_CONTRACT,
            LEGACY_COGNITION_REGISTRATION,
        }:
            raise RuntimeError("unsupported_cognition_contract_version")
        raw_accepted = accepted_core_contract_versions or [CURRENT_COGNITION_CONTRACT]
        if (
            not isinstance(raw_accepted, list)
            or len(raw_accepted) > MAX_COGNITION_CONTRACT_VERSIONS
            or any(not isinstance(item, str) or not _COGNITION_DECLARATION.fullmatch(item) for item in raw_accepted)
        ):
            raise ValueError("invalid_accepted_core_cognition_contracts")
        accepted = tuple(sorted(set(raw_accepted)))
        if CURRENT_COGNITION_CONTRACT not in accepted:
            raise RuntimeError("incompatible_core_cognition_contract")
        if cognition_contract_version == CURRENT_COGNITION_CONTRACT:
            negotiation = self._cognition_negotiation
            if negotiation is None or negotiation.accepted_core_contract_versions != accepted:
                raise RuntimeError("current_cognition_contract_requires_pre_registration_negotiation")
        discipline_values = _bounded_declarations(disciplines, field="disciplines")
        task_type_values = _bounded_declarations(task_types, field="task_types")
        authority_values = _bounded_declarations(required_authorities, field="required_authorities")
        side_effect_values = _bounded_declarations(side_effects, field="side_effects")
        if (
            len(_recipe_disciplines) + len(_recipe_task_types) + len(discipline_values) + len(task_type_values)
            > MAX_COGNITION_ROUTES
        ):
            raise RuntimeError(f"Extension recipe routes are limited to {MAX_COGNITION_ROUTES} entries")
        if name in _recipes:
            raise RuntimeError(f"Recipe '{name}' already registered (existing: {_recipes[name]!r})")
        extension_id = self._extension_id or "legacy-extension"
        extension_version = self._extension_version or "0.0.0"
        definition = RegisteredRecipeSource(
            name=name,
            recipe=recipe,
            extension_id=extension_id,
            extension_version=extension_version,
            disciplines=discipline_values,
            task_types=task_type_values,
            cognition_contract_version=cognition_contract_version,
            accepted_core_contract_versions=accepted,
            package_digest=_recipe_digest(recipe),
            resource_manifest=resources,
            required_authorities=authority_values,
            side_effects=side_effect_values,
            trusted_in_process=trusted_in_process,
            compatibility=(
                "n_minus_1_legacy_adapter" if cognition_contract_version == LEGACY_COGNITION_REGISTRATION else "current"
            ),
        )
        discipline_conflicts = {
            value: _recipe_disciplines[value]
            for value in definition.disciplines
            if value in _recipe_disciplines and _recipe_disciplines[value] != name
        }
        if discipline_conflicts:
            raise RuntimeError(f"Recipe discipline routes conflict: {discipline_conflicts}")
        task_type_conflicts = {
            value: _recipe_task_types[value]
            for value in definition.task_types
            if value in _recipe_task_types and _recipe_task_types[value] != name
        }
        if task_type_conflicts:
            raise RuntimeError(f"Recipe task-type routes conflict: {task_type_conflicts}")
        _recipes[name] = recipe
        _recipe_metadata[name] = definition
        for d in definition.disciplines:
            _recipe_disciplines[d] = name
        for t in definition.task_types:
            _recipe_task_types[t] = name

    def register_committee(self, name: str, builder: Callable[..., Any]) -> None:
        self._record_unsupported("committee", name)

    def register_personas(self, personas: list[Any]) -> None:
        for index, persona in enumerate(personas):
            self._record_unsupported("persona", str(getattr(persona, "slug", None) or index))

    def register_frameworks(self, frameworks: list[Any]) -> None:
        for index, framework in enumerate(frameworks):
            self._record_unsupported("framework", str(getattr(framework, "slug", None) or index))

    def register_tool(self, fn: Callable[..., Any], *, title: str | None = None) -> None:
        _tools.append({"fn": fn, "title": title or getattr(fn, "__name__", "tool")})

    def register_verify_check(self, fn: Callable[[list[dict]], list[dict]]) -> None:
        """Register a verify-time check (see `_verify_checks`). MAKE arms run every
        registered check in verify() and fail closed on enforced violations."""
        _verify_checks.append(fn)

    def register_grounded_state_adapter(self, name: str, adapter: Any) -> None:
        """Register source-specific extraction mapping on the existing E1 seam.

        The adapter is intentionally not a persistence callback.  Consumers ask
        it for a bounded Core manifest and pass that manifest to the Core-owned
        grounded-state ingestion service.
        """
        if not self._extension_id:
            raise RuntimeError("register_grounded_state_adapter requires an extension-scoped Registry")
        if not _ADAPTER_NAME.fullmatch(name):
            raise ValueError("grounded-state adapter name must be a bounded lowercase stable token")
        if not callable(getattr(adapter, "build_manifest", None)):
            raise TypeError("grounded-state adapters must expose a build_manifest callable")
        identity = (self._extension_id, name)
        if identity in _grounded_state_adapters:
            raise RuntimeError(f"Grounded-state adapter '{self._extension_id}:{name}' is already registered")
        if len(_grounded_state_adapters) >= MAX_GROUNDED_STATE_ADAPTERS:
            raise RuntimeError(f"Grounded-state adapter registry is limited to {MAX_GROUNDED_STATE_ADAPTERS} entries")
        _grounded_state_adapters[identity] = adapter

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
        self._record_unsupported("schema", surql_path)

    def _record_unsupported(self, capability: str, stable_key: str) -> None:
        _unsupported_registrations.append(
            UnsupportedRegistration(
                extension_id=self._extension_id or "legacy-extension",
                extension_version=self._extension_version or "0.0.0",
                capability=capability,
                stable_key=stable_key,
            )
        )

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

    def register_task_action(
        self,
        action: str,
        prepare: PrepareTaskAction,
        *,
        project_outcome: ProjectOutcome | None = None,
        validate_outcome: ValidateOutcome | None = None,
        input_contract: str = "extension-invocation-v1",
        accepted_input_contract_versions: list[str] | None = None,
        output_contract: str = "extension-outcome-v1",
        description: str = "",
        lifecycle_operations: list[str] | None = None,
        cancellation_supported: bool = False,
        resolver_capabilities: list[str] | None = None,
        artifact_capabilities: list[str] | None = None,
        required_authority: list[str] | None = None,
        feature_flags: list[str] | None = None,
    ) -> RegisteredTaskAction:
        """Register an extension-owned resolver/projector on Core's task lifecycle.

        ``prepare`` receives the structured invocation envelope plus an
        authenticated actor scope and returns an ``ExtensionTaskPlan``.
        ``project_outcome`` may convert completed output into bounded domain JSON.
        Core remains responsible for idempotency, persistence, attempt lineage,
        provider execution, and the public receipt.

        This method requires the scoped Registry supplied by the extension loader;
        a bare ``Registry()`` cannot claim an extension identity.
        """
        if not self._extension_id or not self._extension_version:
            raise RuntimeError("register_task_action requires an extension-scoped Registry")
        registered = RegisteredTaskAction(
            extension_id=self._extension_id,
            extension_version=self._extension_version,
            action=action,
            prepare=prepare,
            project_outcome=project_outcome,
            validate_outcome=validate_outcome,
            input_contract=input_contract,
            accepted_input_contract_versions=(
                [input_contract] if accepted_input_contract_versions is None else accepted_input_contract_versions
            ),
            output_contract=output_contract,
            description=description,
            lifecycle_operations=(
                ["submit", "retrieve", "history", "retry"] if lifecycle_operations is None else lifecycle_operations
            ),
            cancellation_supported=cancellation_supported,
            resolver_capabilities=resolver_capabilities or [],
            artifact_capabilities=artifact_capabilities or [],
            required_authority=required_authority or [],
            feature_flags=feature_flags or [],
        )
        identity = registered.identity
        if identity in _task_actions:
            raise RuntimeError(f"Task action '{registered.key}' is already registered")
        if len(_task_actions) >= MAX_TASK_ACTIONS:
            raise RuntimeError(f"Task action registry is limited to {MAX_TASK_ACTIONS} actions")
        _task_actions[identity] = registered
        return registered


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


def registered_recipe_sources() -> dict[str, RegisteredRecipeSource]:
    """Return recipe definitions with their extension identity and version."""
    _ensure_extensions_loaded()
    return {
        name: _recipe_metadata.get(
            name,
            RegisteredRecipeSource(
                name=name,
                recipe=recipe,
                extension_id="legacy-extension",
                extension_version="0.0.0",
                disciplines=tuple(d for d, slug in _recipe_disciplines.items() if slug == name),
                task_types=tuple(t for t, slug in _recipe_task_types.items() if slug == name),
                cognition_contract_version=LEGACY_COGNITION_REGISTRATION,
                accepted_core_contract_versions=(CURRENT_COGNITION_CONTRACT,),
                package_digest=_recipe_digest(recipe),
                resource_manifest=(),
                required_authorities=(),
                side_effects=(),
                trusted_in_process=True,
                compatibility="n_minus_1_legacy_adapter",
            ),
        )
        for name, recipe in _recipes.items()
    }


def registered_recipe_disciplines() -> dict[str, str]:
    _ensure_extensions_loaded()
    return dict(_recipe_disciplines)


def registered_recipe_task_types() -> dict[str, str]:
    _ensure_extensions_loaded()
    return dict(_recipe_task_types)


def registered_recipe_manifests() -> dict[str, dict[str, Any]]:
    return {name: source.public_manifest() for name, source in registered_recipe_sources().items()}


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


def registered_unsupported_cognition() -> list[UnsupportedRegistration]:
    _ensure_extensions_loaded()
    return list(_unsupported_registrations)


def registered_briefing_sections() -> list[dict[str, Any]]:
    _ensure_extensions_loaded()
    return list(_briefing_sections)


def registered_verify_checks() -> list[Callable[[list[dict]], list[dict]]]:
    _ensure_extensions_loaded()
    return list(_verify_checks)


def registered_task_actions() -> dict[TaskActionIdentity, RegisteredTaskAction]:
    _ensure_extensions_loaded()
    return dict(_task_actions)


def registered_grounded_state_adapters() -> dict[GroundedStateAdapterIdentity, Any]:
    _ensure_extensions_loaded()
    return dict(_grounded_state_adapters)


def registered_grounded_state_adapter(extension_id: str, name: str) -> Any | None:
    _ensure_extensions_loaded()
    return _grounded_state_adapters.get((extension_id, name))


def registered_task_action(extension_id: str, action: str) -> RegisteredTaskAction | None:
    _ensure_extensions_loaded()
    return _task_actions.get((extension_id, action))
