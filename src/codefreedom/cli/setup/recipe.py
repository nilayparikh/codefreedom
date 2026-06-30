"""Recipe subsystem — thin CLI entry point that delegates to the recipe subpackage."""
from __future__ import annotations

from codefreedom.recipe.apply import (  # noqa: F401
    _install_recipe_files,
    _print_summary,
    apply_plan,
)
from codefreedom.recipe.merge import (  # noqa: F401
    _deepdiff_merge,
    _merge_env,
    _recursive_merge,
)
from codefreedom.recipe.plan import (  # noqa: F401
    init_recipe,
    list_recipes,
    plan_and_apply_recipe,
    plan_recipe,
    seed_cf_yaml,
    _unify_profiles_yaml,
)
from codefreedom.recipe.store import (  # noqa: F401
    _fetch_recipe_files,
    _fetch_recipe_manifest,
    _find_local_recipe,
    _list_recipes_from_store,
    _parse_github_url,
    _resolve_recipe,
    _resolve_store,
)
