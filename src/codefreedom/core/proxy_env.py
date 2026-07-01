"""Shared proxy compose-env builder.

Single source of truth for the environment dict passed to ``docker compose``
subprocess invocations. Used by ``cli/run/proxy.py`` (start/stop/restart/
status) and ``cli/setup/deinit.py`` (proxy teardown) so both paths resolve
``SUFFIX_ID`` / ``PROXY_*`` / ``COMPOSE_PROJECT_NAME`` *identically*.

Precedence (highest wins):

  1. ``CF_CLI_*`` machine-env overrides
  2. ``override.yaml`` + ``recipe.yaml`` + ``profiles.yaml`` (via
     :func:`codefreedom.config.load_config` → ``for_component("proxy")`)
  3. bare ``os.environ`` for non-config-controlled keys (compose still
     needs paths, TLS settings, etc.)

Previously proxy.py started from ``dict(os.environ)`` and used ``setdefault``
to inject ``SUFFIX_ID``, which let a stray ``SUFFIX_ID`` already exported
in the shell silently *win over* the user's ``override.yaml`` value.
Errors from :func:`load_config` were also swallowed by ``except Exception``
and silently fell back to ``"0000"``, masking schema errors. Both defects
produced ``codefreedom-proxy-0000`` even when ``override.yaml`` set
``SUFFIX_ID: "windemo"``. That is now fixed here.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict

from codefreedom.config import load_config
from codefreedom.config.errors import ConfigError
from codefreedom.config.runtime import apply_cf_cli_overrides
from codefreedom.core.config import get_codefreedom_dir
from codefreedom.log import eprint, tag

# Schema defaults mirrored from config.models.ProxySettings / CommonSection —
# used only when ``load_config()`` itself cannot be executed (e.g. the user's
# config files are missing or invalid). They MUST match
# ``ProxySettings.bind_host``/``bind_port``/``CommonSection.suffix_id`` so the
# fallback is indistinguishable from the schema default.
_DEFAULT_SUFFIX_ID = "0000"
_DEFAULT_BIND_HOST = "0.0.0.0"
_DEFAULT_BIND_PORT = "4000"
_DEFAULT_CONTAINER_NAME = "codefreedom-proxy"
_DEFAULT_PROJECT_NAME = f"codefreedom-{_DEFAULT_SUFFIX_ID}"


def build_proxy_run_env() -> dict[str, str]:
    """Build the merged environment for a ``docker compose`` proxy invocation.

    Exports the full resolved ``vars:`` chain (recipe.yaml -> override.yaml ->
    .cf.yaml -> CF_CLI_*) so docker-compose ``${VAR:-default}`` interpolation
    sees the same values the in-process interpolator used. Structured proxy
    fields (``common.proxy.*``, ``common.suffix_id``) then win over flat vars
    for proxy-specific keys, and ``CF_CLI_*`` overrides are applied *last*.

    Precedence (highest wins):

      1. ``CF_CLI_*`` machine-env overrides
      2. ``for_component("proxy")`` (structured ``common.proxy.*`` +
         ``common.suffix_id``)
      3. resolved ``vars:`` (recipe.yaml -> override.yaml -> .cf.yaml)
      4. bare ``os.environ`` (paths, TLS settings, etc.)

    Config-derived values (``SUFFIX_ID``, ``PROXY_BIND_HOST``,
    ``PROXY_PORT``, ``COMPOSE_PROJECT_NAME``) always overwrite any stray
    values present in bare :data:`os.environ`, so a value leaked into
    the shell can no longer shadow the user's ``override.yaml`` ``vars:`` block.

    On :class:`ConfigError` we surface a warning (rather than silently
    masking the symptom) and fall back to the schema defaults above.
    """
    cf_dir = get_codefreedom_dir()
    merged: Dict[str, str] = dict(os.environ)
    merged.setdefault("POSTGRES_HOST_DATA_DIR", str(cf_dir / "pg" / "data"))
    merged.setdefault("POSTGRES_HOST_BACKUP_DIR", str(cf_dir / "pg" / "backup"))

    proxy_env: Dict[str, str] = {
        "SUFFIX_ID": _DEFAULT_SUFFIX_ID,
        "PROXY_BIND_HOST": _DEFAULT_BIND_HOST,
        "PROXY_PORT": _DEFAULT_BIND_PORT,
        "COMPOSE_PROJECT_NAME": _DEFAULT_PROJECT_NAME,
    }
    try:
        config = load_config()
        # Export ALL resolved vars (recipe/override/.cf.yaml) so docker-compose
        # ${VAR:-default} interpolation sees them. Without this, vars like
        # OPENCODE_SUB_ROUTING_ORDER set in .cf.yaml never reach the proxy
        # container even though `cf m dr` displays them.
        merged.update(config.vars)
        # Structured proxy fields win over flat vars for proxy-specific keys
        # (PROXY_BIND_HOST, PROXY_PORT, PROXY_BASE_URL, SUFFIX_ID,
        # COMPOSE_PROJECT_NAME, plus common.proxy.env entries).
        proxy_env = dict(config.for_component("proxy"))
    except ConfigError as exc:
        eprint(
            f"{tag('PROXY')} Warning: proxy config could not be loaded ({exc}); "
            "using schema defaults (suffix=0000, 0.0.0.0:4000)."
        )

    merged.update(proxy_env)
    merged = apply_cf_cli_overrides(merged)

    # Container bridge: the LiteLLM container reads ``LITELLM_MASTER_KEY`` for
    # auth (LiteLLM's own convention). CodeFreedom's canonical secret is
    # ``PROXY_API_KEY``. Mirror whichever is set so the container always
    # receives its master key, regardless of which name the user exported.
    bridge_key = merged.get("LITELLM_MASTER_KEY") or merged.get("PROXY_API_KEY", "")
    if bridge_key:
        merged.setdefault("LITELLM_MASTER_KEY", bridge_key)
        merged.setdefault("PROXY_API_KEY", bridge_key)

    host = merged.get("PROXY_BIND_HOST", _DEFAULT_BIND_HOST)
    port = merged.get("PROXY_PORT", _DEFAULT_BIND_PORT)
    merged.setdefault("PROXY_PUBLIC_BASE_URL", f"http://{host}:{port}")
    return merged


def proxy_container_name(merged_env: dict[str, str]) -> str:
    """Compose the proxy container name (``codefreedom-proxy-{suffix}``).

    The suffix is sourced from the already-resolved ``SUFFIX_ID`` in
    ``merged_env``. The base name (``PROXY_CONTAINER_NAME``) lets a user
    override the entire prefix; the suffix is always appended.
    """
    suffix = merged_env.get("SUFFIX_ID", _DEFAULT_SUFFIX_ID)
    base = merged_env.get("PROXY_CONTAINER_NAME", _DEFAULT_CONTAINER_NAME)
    # ``PROXY_CONTAINER_NAME`` from config is the bare base (e.g.
    # ``codefreedom-proxy``); the running container always appends suffix.
    # Strip any existing suffix to avoid double-appending on restart.
    if base.endswith(f"-{suffix}"):
        return base
    return f"{base}-{suffix}"


# ── Compose template refresh ─────────────────────────────────────────────────


# Marker that distinguishes a templated compose file (honours the vars chain)
# from a stale hardcoded one. ``${PROXY_BIND_HOST`` only appears in the
# templated ``ports:`` line; hardcoded files have a literal like
# ``127.0.0.1:4000:4000`` which bypasses the config chain.
_TEMPLATE_MARKER = "${PROXY_BIND_HOST"


def _bundled_compose_template() -> str:
    """Return the bundled ``docker-compose.yaml`` template content.

    Shipped inside the installed package at
    ``codefreedom/templates/proxy/docker-compose.yaml`` so the refresh works
    even when the recipe store is absent (e.g. wheel-only install).
    """
    import importlib.resources

    pkg = importlib.resources.files("codefreedom.templates.proxy")
    return pkg.joinpath("docker-compose.yaml").read_text(encoding="utf-8")


def _recipe_store_compose_template() -> str | None:
    """Return a compose template from the recipe store, if present.

    Scans ``~/.codefreedom/stores/*/*/proxy/docker-compose.yaml`` for a
    templated file (one carrying :data:`_TEMPLATE_MARKER`). Returns the first
    match, else ``None``. The recipe store is the canonical source when the
    user has applied a recipe; the bundled template is the fallback.
    """
    cf_dir = get_codefreedom_dir()
    stores_dir = cf_dir / "stores"
    if not stores_dir.is_dir():
        return None
    for candidate in sorted(stores_dir.glob("*/*/proxy/docker-compose.yaml")):
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        if _TEMPLATE_MARKER in content:
            return content
    return None


def is_compose_stale(compose_path: Path) -> bool:
    """Return True if the installed compose file is hardcoded (not templated).

    A templated file uses ``${PROXY_BIND_HOST:-...}`` so docker-compose
    interpolation honours the ``override.yaml`` / ``.cf.yaml`` vars chain.
    A stale file has a literal ``127.0.0.1:4000:4000`` ports line and
    hardcoded provider settings, which silently bypass the config chain.
    """
    try:
        content = compose_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return _TEMPLATE_MARKER not in content


def refresh_compose_template(compose_path: Path) -> bool:
    """Refresh a stale hardcoded compose file to the templated form.

    Source priority:
      1. Recipe store template (``~/.codefreedom/stores/.../proxy/docker-compose.yaml``)
      2. Bundled package template (``codefreedom/templates/proxy/docker-compose.yaml``)

    The old file is backed up to ``<name>.bak`` before overwrite. Returns
    ``True`` if the file was refreshed, ``False`` if it was already templated
    or no template source was available.
    """
    if not compose_path.exists():
        return False
    if not is_compose_stale(compose_path):
        return False

    template = _recipe_store_compose_template()
    if template is None:
        try:
            template = _bundled_compose_template()
        except (FileNotFoundError, OSError, ModuleNotFoundError):
            eprint(
                f"{tag('PROXY')} Warning: could not load bundled compose template;"
                " stale docker-compose.yaml left untouched."
            )
            return False

    backup = compose_path.with_suffix(compose_path.suffix + ".bak")
    try:
        shutil.copy2(compose_path, backup)
    except OSError as exc:
        eprint(
            f"{tag('PROXY')} Warning: could not back up {compose_path} ({exc});"
            " stale docker-compose.yaml left untouched."
        )
        return False

    try:
        compose_path.write_text(template, encoding="utf-8")
    except OSError as exc:
        eprint(
            f"{tag('PROXY')} Warning: could not refresh {compose_path} ({exc});"
            " stale docker-compose.yaml left untouched."
        )
        return False

    eprint(
        f"{tag('PROXY')} Refreshed docker-compose.yaml from template"
        f" (previous version backed up to {backup.name})."
    )
    eprint(
        "   Hardcoded literals were replaced with ${VAR:-default} so"
        " override.yaml / .cf.yaml vars now take effect."
    )
    return True


def ensure_compose_template(compose_path: Path) -> None:
    """Refresh the compose file if stale; no-op when already templated.

    Called by ``cf run proxy start`` (and ``cf manage update``) so a user who
    edits a value in ``.cf.yaml`` and runs ``cf r px restart`` sees the new
    value take effect — even if their installed compose file predates the
    templating fix.
    """
    refresh_compose_template(compose_path)
