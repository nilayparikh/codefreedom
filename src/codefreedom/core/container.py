"""Container / tool lifecycle helpers — canonical facade.

This module is the **programmatic interface** for the tool modules
(``tools/chrome.py`` etc.) and for any code outside ``cli/`` that needs to
inspect Docker container state. It re-exports the helpers that live in
:mod:`codefreedom.cli.docker_utils`; the implementation stays there for now
to avoid breaking call sites in tests and other ``cli/`` modules.

Why a facade at all?

* The AGENTS.md layer model says ``tools/`` may only call the layer below
  it (``core/``), never ``cli/`` sideways. Direct ``from
  codefreedom.cli.docker_utils import ...`` in ``tools/*`` was a layering
  violation; this facade gives tools a stable ``core.container`` import path.
* Future passes will physically relocate the implementation into
  :mod:`codefreedom.core.container_impl` (or split into
  ``core/container.py`` + ``core/tool_lifecycle.py``); the imports already
  point at ``codefreedom.core.container`` so they won't churn again.

Anything imported here is part of the public tool-lifecycle contract:
  - ``container_is_running``, ``container_exists``, ``check_docker_available``
  - ``ensure_image``, ``find_containers_by_base``, ``generate_container_name``
  - ``is_port_available``, ``get_codefreedom_container_ports``
  - ``get_profiles_path``, ``tool_home``, ``tool_data_dir``, ``resolve_data_dir``
  - ``TOOL_INFO``, ``print_tool_notice``
  - ``load_tool_profile``, ``init_tool_redirect``
  - ``start_tool_container``, ``stop_tool_container``,
    ``restart_tool_container``, ``status_tool_container``
  - ``start_tool_init_gate``, ``start_tool_docker_guard``,
    ``start_tool_remove_stopped``, ``start_tool_ensure_image``
"""

from __future__ import annotations

# Facade imports — symbols owned physically by ``cli.docker_utils`` for now.
from codefreedom.cli.docker_utils import (  # noqa: F401
    TOOL_INFO,
    accept_tool_prompt,
    check_docker_available,
    container_exists,
    container_is_running,
    ensure_image,
    find_containers_by_base,
    generate_container_name,
    get_codefreedom_container_ports,
    get_profiles_path,
    init_tool_redirect,
    is_port_available,
    load_tool_profile,
    print_help_section,
    print_tool_notice,
    resolve_data_dir,
    restart_tool_container,
    start_tool_container,
    start_tool_docker_guard,
    start_tool_ensure_image,
    start_tool_init_gate,
    start_tool_remove_stopped,
    status_tool_container,
    stop_tool_container,
    tool_data_dir,
    tool_home,
)