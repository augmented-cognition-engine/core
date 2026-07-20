"""YAML recipe loader — discover, parse, validate, convert.

Three public functions:

  load_yaml_recipe_file(path) -> MetaSkill
      Parse one YAML file. Raises on syntax/validation errors.

  discover_yaml_recipes(directory) -> list[tuple[Path, MetaSkill]]
      Glob *.yaml in a directory. Bad files are logged CRITICAL and
      skipped so one broken recipe never crashes startup.

  discover_core_yaml_recipes() -> None
      Convenience wrapper that scans the core recipes/ directory and
      populates composer._RECIPE_YAML. Idempotent (early-returns if
      _RECIPE_YAML is already populated). Called at composer module
      load time.

Note: discover_core_yaml_recipes() fires when composer.py is imported,
not when this loader module is imported. Anyone loading recipes via
this module's primitive functions directly will NOT trigger global
discovery.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from core.engine.cognition.models import MetaSkill
from core.engine.cognition.recipes.schema import RecipeYAMLSchema

logger = logging.getLogger(__name__)


def load_yaml_recipe_file(path: Path) -> MetaSkill:
    """Parse one YAML recipe file into a MetaSkill. Raises on errors."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    schema = RecipeYAMLSchema.model_validate(data)
    return schema.to_meta_skill()


def load_yaml_recipe_with_routing(path: Path) -> tuple[MetaSkill, dict[str, list[str]]]:
    """Parse one YAML recipe file into a MetaSkill plus its routing metadata.

    Returns ``(meta_skill, routing)`` where routing is a dict with keys
    ``disciplines`` and ``task_types`` (each a list of strings, empty if
    the YAML omits the ``routing:`` block).

    Used by extension activation hooks so the flavor can pass YAML-declared
    routing into ``Registry.register_recipe(disciplines=..., task_types=...)``
    instead of hardcoding the values in Python. Keeps recipes self-describing.
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    schema = RecipeYAMLSchema.model_validate(data)
    routing = {
        "disciplines": schema.routing.disciplines if schema.routing else [],
        "task_types": schema.routing.task_types if schema.routing else [],
    }
    return schema.to_meta_skill(), routing


def discover_yaml_recipes(directory: Path) -> list[tuple[Path, MetaSkill]]:
    """Discover all *.yaml files in a directory. Skip-and-log bad files."""
    results: list[tuple[Path, MetaSkill]] = []
    if not directory.is_dir():
        return results
    for path in sorted(directory.glob("*.yaml")):
        try:
            meta_skill = load_yaml_recipe_file(path)
        except yaml.YAMLError as exc:
            logger.critical("YAML syntax error in %s: %s", path, exc)
            continue
        except ValidationError as exc:
            logger.critical("Validation error in %s: %s", path, exc)
            continue
        except Exception as exc:  # defensive: never let one file crash startup
            logger.critical("Unexpected error loading recipe %s: %s", path, exc)
            continue
        results.append((path, meta_skill))
    return results


def discover_core_yaml_recipes() -> None:
    """Scan core recipes/ and inject parsed MetaSkills into composer._RECIPE_YAML.

    Idempotent — early-returns if _RECIPE_YAML is already populated. Detects
    slug collisions against the kernel's _RECIPE_MODULES map (Python recipes)
    AND against any previously-loaded YAML file in the same scan. Raises
    RuntimeError naming both sources so the developer knows what to remove.
    Imported lazily inside the function to avoid an import cycle with composer.
    """
    from core.engine.cognition import composer

    if composer._RECIPE_YAML:
        return

    core_dir = Path(__file__).parent
    seen_paths: dict[str, Path] = {}
    for path, meta_skill in discover_yaml_recipes(core_dir):
        slug = meta_skill.slug
        if slug in composer._RECIPE_MODULES:
            raise RuntimeError(
                f"Recipe slug collision: '{slug}' is registered as both "
                f"a core Python module ({composer._RECIPE_MODULES[slug]}) "
                f"and a YAML file ({path}). Resolve by removing one."
            )
        if slug in seen_paths:
            raise RuntimeError(
                f"Recipe slug collision: '{slug}' is defined in two YAML "
                f"files: {seen_paths[slug]} and {path}. Resolve by removing one."
            )
        seen_paths[slug] = path
        composer._RECIPE_YAML[slug] = meta_skill
        logger.info("Loaded YAML recipe '%s' from %s", slug, path)
