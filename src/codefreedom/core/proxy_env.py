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

    Config-derived values (``SUFFIX_ID``, ``PROXY_BIND_HOST``,
    ``PROXY_PORT``, ``COMPOSE_PROJECT_NAME``) always overwrite any stray
    values present in bare :data:`os.environ`, so a value leaked into
    the shell can no longer shadow the user's ``override.yaml`` ``vars:`` block.
    ``CF_CLI_*`` overrides are applied *last* and win over everything else.

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
        proxy_env = dict(load_config().for_component("proxy"))
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
