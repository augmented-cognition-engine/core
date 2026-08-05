"""Deterministic adapters from current recipe sources into canonical revisions."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.engine.cognition.contracts import (
    RECIPE_BODY_VERSION,
    CognitionDependencyV1,
    CognitionHeadV1,
    CognitionIdentityV1,
    CognitionOwnerV1,
    CognitionRevisionV1,
    CognitionScopeV1,
    CognitionSourceV1,
    CognitionType,
    OwnerKind,
    ScopeKind,
    canonical_hash,
)
from core.engine.cognition.models import (
    CaptureSpec,
    ContextQuery,
    InstrumentSpec,
    MetaSkill,
    MetaSkillRecipe,
    RecipePhase,
    ToolSpec,
)
from core.engine.cognition.store import CognitionIdentityConflict
from core.engine.version import VERSION

CORE_RECIPE_MODULES: dict[str, str] = {
    "creative_intelligence": "core.engine.cognition.recipes.creative",
    "research_intelligence": "core.engine.cognition.recipes.research",
    "coding_intelligence": "core.engine.cognition.recipes.coding",
    "evaluation_intelligence": "core.engine.cognition.recipes.evaluation",
    "strategic_intelligence": "core.engine.cognition.recipes.strategic",
    "communication_intelligence": "core.engine.cognition.recipes.communication",
    "systems_intelligence": "core.engine.cognition.recipes.systems",
    "data_intelligence": "core.engine.cognition.recipes.data",
    "retrieval_intelligence": "core.engine.cognition.recipes.retrieval",
    "planning_intelligence": "core.engine.cognition.recipes.planning",
    "delegation_intelligence": "core.engine.cognition.recipes.delegation",
    "risk_intelligence": "core.engine.cognition.recipes.risk",
    "gap_intelligence": "core.engine.cognition.recipes.gap",
    "feedback_intelligence": "core.engine.cognition.recipes.feedback",
    "verification_intelligence": "core.engine.cognition.recipes.verification",
    "memory_intelligence": "core.engine.cognition.recipes.memory",
    "coordination_intelligence": "core.engine.cognition.recipes.coordination",
    "tool_intelligence": "core.engine.cognition.recipes.tool",
    "communication_agentic_intelligence": "core.engine.cognition.recipes.communication_agentic",
    "operational_intelligence": "core.engine.cognition.recipes.operational",
    "domain_specific_intelligence": "core.engine.cognition.recipes.domain_specific",
}


@dataclass(frozen=True)
class AdaptedRecipe:
    revision: CognitionRevisionV1
    head: CognitionHeadV1
    runtime_view: MetaSkill
    disciplines: tuple[str, ...] = ()
    task_types: tuple[str, ...] = ()


def meta_skill_from_body(body: dict[str, Any]) -> MetaSkill:
    """Rebuild the temporary execution view from an exact recipe body."""
    phases: list[RecipePhase] = []
    for phase_body in body.get("recipe", {}).get("phases", []):
        context = phase_body.get("load_context")
        capture = phase_body.get("capture_as")
        phases.append(
            RecipePhase(
                cognitive_function=phase_body["cognitive_function"],
                instruments=[InstrumentSpec(**item) for item in phase_body.get("instruments", [])],
                min_depth=phase_body["min_depth"],
                output_schema=phase_body["output_schema"],
                pattern=phase_body.get("pattern", "solo"),
                must_not=list(phase_body.get("must_not") or []),
                must_verify=list(phase_body.get("must_verify") or []),
                load_context=ContextQuery(**context) if context else None,
                capture_as=CaptureSpec(**capture) if capture else None,
                tools=[ToolSpec(**item) for item in phase_body.get("tools", [])],
                signature=phase_body.get("signature", 0.5),
            )
        )
    return MetaSkill(
        slug=body["slug"],
        name=body["name"],
        description=body["description"],
        domain_intelligences=list(body.get("domain_intelligences") or []),
        recipe=MetaSkillRecipe(phases=phases),
        min_execution_depth=body.get("min_execution_depth", 1),
        activation_signals=list(body.get("activation_signals") or []),
        archetype_affinity=dict(body.get("archetype_affinity") or {}),
        mode_affinity=dict(body.get("mode_affinity") or {}),
        composability={key: list(value) for key, value in (body.get("composability") or {}).items()},
    )


def _bytes_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _module_source(module_path: str, *, package_id: str | None, package_version: str | None) -> CognitionSourceV1:
    spec = importlib.util.find_spec(module_path)
    origin = spec.origin if spec is not None else None
    if origin and Path(origin).is_file():
        digest = _bytes_hash(Path(origin).read_bytes())
        locator = module_path
    else:
        digest = _bytes_hash(module_path.encode("utf-8"))
        locator = module_path
    return CognitionSourceV1(
        source_kind="python_module",
        locator=locator,
        content_hash=digest,
        package_id=package_id,
        package_version=package_version,
    )


def _yaml_source(slug: str, meta_skill: MetaSkill) -> CognitionSourceV1:
    path = Path(__file__).parent / "recipes" / f"{slug.removesuffix('_intelligence')}.yaml"
    if path.is_file():
        return CognitionSourceV1(
            source_kind="yaml_file",
            locator=str(path),
            content_hash=_bytes_hash(path.read_bytes()),
            package_id="ace-core",
            package_version=VERSION,
        )
    material = asdict(meta_skill)
    return CognitionSourceV1(
        source_kind="legacy_memory_adapter",
        locator=f"memory:{slug}",
        content_hash=canonical_hash(material),
        package_id="ace-core",
        package_version=VERSION,
    )


def _dependencies(meta_skill: MetaSkill, *, default_owner_namespace: str) -> tuple[CognitionDependencyV1, ...]:
    from core.engine.cognition.instrument_registry import registered_instrument_metadata

    python_instruments = registered_instrument_metadata()
    out: list[CognitionDependencyV1] = []
    seen: set[tuple[str, str, str]] = set()

    def add(cognition_type: CognitionType, stable_key: str, owner_namespace: str) -> None:
        identity = (cognition_type.value, stable_key, owner_namespace)
        if identity in seen:
            return
        seen.add(identity)
        out.append(
            CognitionDependencyV1(
                cognition_type=cognition_type,
                stable_key=stable_key,
                owner_namespace=owner_namespace,
            )
        )

    for phase in meta_skill.recipe.phases:
        for spec in phase.instruments:
            for slug in (spec.slug, spec.fallback_slug):
                if not slug:
                    continue
                registration = python_instruments.get(slug)
                if registration is not None:
                    owner_namespace = (
                        f"extension:{registration.extension_id}"
                        if registration.extension_id
                        else default_owner_namespace
                    )
                    add(CognitionType.INSTRUMENT, slug, owner_namespace)
                else:
                    add(CognitionType.FRAMEWORK, slug, "core:frameworks")
        for spec in phase.tools:
            for slug in (spec.slug, spec.fallback_slug):
                if slug:
                    add(CognitionType.TOOL, slug, "core:tools")
    return tuple(out)


def adapt_recipe(
    meta_skill: MetaSkill,
    *,
    owner: CognitionOwnerV1,
    scope: CognitionScopeV1,
    source: CognitionSourceV1,
    authority_receipt_id: str,
    disciplines: tuple[str, ...] = (),
    task_types: tuple[str, ...] = (),
) -> AdaptedRecipe:
    identity = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=owner,
        stable_key=meta_skill.slug,
    )
    revision = CognitionRevisionV1(
        identity=identity,
        body_schema_version=RECIPE_BODY_VERSION,
        body=asdict(meta_skill),
        dependencies=_dependencies(meta_skill, default_owner_namespace=owner.namespace),
        sources=(source,),
        approval_receipt_id=authority_receipt_id,
    )
    head = CognitionHeadV1(
        cognition_id=str(identity.cognition_id),
        scope=scope,
        active_revision_id=str(revision.revision_id),
        authority_receipt_id=authority_receipt_id,
    )
    return AdaptedRecipe(
        revision=revision,
        head=head,
        runtime_view=meta_skill,
        disciplines=tuple(sorted(set(disciplines))),
        task_types=tuple(sorted(set(task_types))),
    )


def adapt_all_recipes(core_yaml: dict[str, MetaSkill] | None = None) -> tuple[AdaptedRecipe, ...]:
    """Normalize every current Core/YAML/extension recipe and reject aliases."""
    adapted: list[AdaptedRecipe] = []
    by_slug: dict[str, AdaptedRecipe] = {}

    core_owner = CognitionOwnerV1(kind=OwnerKind.CORE, namespace="core:ace", provenance=f"ace-core:{VERSION}")
    core_scope = CognitionScopeV1(kind=ScopeKind.CORE_DEFAULT)
    for expected_slug, module_path in sorted(CORE_RECIPE_MODULES.items()):
        module = importlib.import_module(module_path)
        meta_skill = module.get_meta_skill()
        if not isinstance(meta_skill, MetaSkill) or meta_skill.slug != expected_slug:
            raise CognitionIdentityConflict(f"malformed_cognition:{expected_slug}:{module_path}")
        item = adapt_recipe(
            meta_skill,
            owner=core_owner,
            scope=core_scope,
            source=_module_source(module_path, package_id="ace-core", package_version=VERSION),
            authority_receipt_id=f"core_release_manifest:ace-core:{VERSION}",
        )
        adapted.append(item)
        by_slug[expected_slug] = item

    for slug, meta_skill in sorted((core_yaml or {}).items()):
        if meta_skill.slug != slug:
            raise CognitionIdentityConflict(f"malformed_cognition:{slug}:yaml_slug_mismatch")
        if slug in by_slug:
            raise CognitionIdentityConflict(f"cognition_identity_conflict:{slug}:core_python_and_yaml")
        item = adapt_recipe(
            meta_skill,
            owner=core_owner,
            scope=core_scope,
            source=_yaml_source(slug, meta_skill),
            authority_receipt_id=f"core_release_manifest:ace-core:{VERSION}",
        )
        adapted.append(item)
        by_slug[slug] = item

    from core.engine.extensions.registry import registered_recipe_sources

    for name, definition in sorted(registered_recipe_sources().items()):
        value: Any = definition.recipe
        if isinstance(value, str):
            module = importlib.import_module(value)
            meta_skill = module.get_meta_skill()
            source = _module_source(
                value,
                package_id=definition.extension_id,
                package_version=definition.extension_version,
            )
        elif isinstance(value, MetaSkill):
            meta_skill = value
            source = CognitionSourceV1(
                source_kind="extension_object",
                locator=f"extension:{definition.extension_id}:{name}",
                content_hash=canonical_hash(asdict(meta_skill)),
                package_id=definition.extension_id,
                package_version=definition.extension_version,
            )
        else:
            raise CognitionIdentityConflict(f"malformed_cognition:{name}:unsupported_recipe_source")
        if meta_skill.slug != name:
            raise CognitionIdentityConflict(f"malformed_cognition:{name}:registered_slug_mismatch")
        if name in by_slug:
            raise CognitionIdentityConflict(f"cognition_identity_conflict:{name}:core_extension_alias")
        namespace = f"extension:{definition.extension_id}"
        item = adapt_recipe(
            meta_skill,
            owner=CognitionOwnerV1(
                kind=OwnerKind.EXTENSION,
                namespace=namespace,
                provenance=f"{definition.extension_id}:{definition.extension_version}",
            ),
            scope=CognitionScopeV1(kind=ScopeKind.EXTENSION_DEFAULT, extension_id=definition.extension_id),
            source=source,
            authority_receipt_id=(f"extension_manifest:{definition.extension_id}:{definition.extension_version}"),
            disciplines=definition.disciplines,
            task_types=definition.task_types,
        )
        adapted.append(item)
        by_slug[name] = item

    return tuple(adapted)
