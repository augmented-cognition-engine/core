"""Recipe modules — one per meta-skill.

Recipes can be authored as either Python modules or YAML files in this
directory. Both forms resolve through CognitiveComposer._load_recipe().

Python recipes
--------------
Each module exports a single function::

    def get_meta_skill() -> MetaSkill: ...

The module path is registered in composer._RECIPE_MODULES.

YAML recipes
------------
Each ``*.yaml`` file in this directory is discovered, validated against
the Pydantic schema in ``schema.py``, and registered in
``composer._RECIPE_YAML`` when ``composer`` is imported (the loader's
``discover_core_yaml_recipes()`` runs at that point and is idempotent).

A minimal recipe looks like::

    slug: my_recipe_intelligence
    name: My Recipe Intelligence
    description: One sentence describing what this meta-skill does.
    domain_intelligences: [planning]
    min_execution_depth: 1
    recipe:
      phases:
        - cognitive_function: frame
          pattern: solo
          min_depth: 1
          output_schema: framed_problem
          instruments:
            - fallback_slug: mece

Field mapping is 1:1 with the dataclasses in
``core.engine.cognition.models``. Unknown fields are rejected
(``extra="forbid"``). Slug collision with any other recipe (Python or
YAML, core or extension) raises RuntimeError at startup.

Extension YAML recipes live under ``extensions/<name>/recipes/`` and are
loaded by the extension's flavor via ``load_yaml_recipe_file()`` and
registered through ``Registry.register_recipe(slug, meta_skill, ...)``.
The composer resolves them via the same ``_load_recipe()`` path that
serves core recipes.
"""
