"""Canonical governed-cognition read boundary used by the composer."""

from __future__ import annotations

from dataclasses import dataclass

from core.engine.cognition.contracts import CognitionRevisionV1
from core.engine.cognition.legacy_adapters import AdaptedRecipe, adapt_all_recipes
from core.engine.cognition.models import MetaSkill
from core.engine.cognition.store import CognitionIdentityConflict, InMemoryCognitionStore


@dataclass(frozen=True)
class CatalogRecipeView:
    slug: str
    revision: CognitionRevisionV1
    runtime_view: MetaSkill
    disciplines: tuple[str, ...]
    task_types: tuple[str, ...]


class CognitionCatalog:
    """Typed catalog with exact active revisions and legacy execution views."""

    def __init__(
        self,
        recipes: tuple[AdaptedRecipe, ...],
        *,
        store: InMemoryCognitionStore | None = None,
    ) -> None:
        self.store = store or InMemoryCognitionStore()
        self._recipes: dict[str, CatalogRecipeView] = {}
        self._discipline_routes: dict[str, str] = {}
        self._task_type_routes: dict[str, str] = {}
        for recipe in recipes:
            self._add_recipe(recipe)

    def _add_recipe(self, adapted: AdaptedRecipe) -> None:
        slug = adapted.runtime_view.slug
        if slug in self._recipes:
            raise CognitionIdentityConflict(f"cognition_identity_conflict:{slug}:catalog_alias")
        self.store.add_revision(adapted.revision, runtime_view=adapted.runtime_view)
        self.store.activate(adapted.head)
        view = CatalogRecipeView(
            slug=slug,
            revision=adapted.revision,
            runtime_view=adapted.runtime_view,
            disciplines=adapted.disciplines,
            task_types=adapted.task_types,
        )
        self._recipes[slug] = view
        for discipline in adapted.disciplines:
            existing = self._discipline_routes.get(discipline)
            if existing is not None and existing != slug:
                raise CognitionIdentityConflict(f"cognition_route_conflict:discipline:{discipline}:{existing}:{slug}")
            self._discipline_routes[discipline] = slug
        for task_type in adapted.task_types:
            existing = self._task_type_routes.get(task_type)
            if existing is not None and existing != slug:
                raise CognitionIdentityConflict(f"cognition_route_conflict:task_type:{task_type}:{existing}:{slug}")
            self._task_type_routes[task_type] = slug

    def recipe_slugs(self) -> tuple[str, ...]:
        return tuple(sorted(self._recipes))

    def recipe_views(self) -> tuple[CatalogRecipeView, ...]:
        return tuple(self._recipes[slug] for slug in sorted(self._recipes))

    def recipe(self, slug: str) -> MetaSkill | None:
        item = self._recipes.get(slug)
        return item.runtime_view if item is not None else None

    def recipe_revision(self, slug: str) -> CognitionRevisionV1 | None:
        item = self._recipes.get(slug)
        return item.revision if item is not None else None

    def recipe_view(self, slug: str) -> CatalogRecipeView | None:
        return self._recipes.get(slug)

    def route_recipe(self, *, task_type: str, discipline: str) -> str | None:
        return self._task_type_routes.get(task_type) or self._discipline_routes.get(discipline)

    def manifest(self) -> tuple[tuple[str, str, str], ...]:
        """Return a deterministic slug/stable/revision identity manifest."""
        return tuple(
            (
                slug,
                str(view.revision.identity.cognition_id),
                str(view.revision.revision_id),
            )
            for slug, view in sorted(self._recipes.items())
        )


def build_default_catalog(*, core_yaml: dict[str, MetaSkill] | None = None) -> CognitionCatalog:
    """Build a fresh catalog from current authoring sources through adapters."""
    return CognitionCatalog(adapt_all_recipes(core_yaml=core_yaml))
