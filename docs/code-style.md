# Code Style Standards

Internal coding conventions for the CodeFreedom CLI project.

## 1. Module Organization

```text
src/codefreedom/
├── __init__.py          # __version__ from importlib.metadata
├── __main__.py          # python -m entry point
├── log.py               # tag(), eprint(), colored output
├── launcher.py          # Docker and native local execution
├── config/              # Configuration module (single source of truth)
│   ├── __init__.py      # Public API: load_config(), error types, models
│   ├── errors.py        # ConfigError, MissingSecretError, ProfileError
│   ├── interpolation.py # ${VAR} resolution: resolve_var(), interpolate_all()
│   ├── loader.py        # load_config(), ResolvedConfig, AgentConfig, ToolConfig
│   ├── models.py        # Pydantic schema: ConfigModel, ProfileEntry, etc.
│   ├── runtime.py       # resolve_agent_runtime(), list_profiles(), settings
│   ├── display.py       # Config display/formatting helpers
│   └── yaml_utils.py    # safe_load(), safe_dump()
├── core/                # Leaf modules (no intra-package deps)
│   ├── config.py        # CODEFREEDOM_HOME resolution
│   ├── http_client.py   # Shared HTTP client utilities
│   ├── container.py     # Canonical facade for tool lifecycle helpers
│   ├── agent_runtime.py # detect_proxy_url(), fetch_proxy_models()
│   ├── proxy_env.py     # Proxy environment resolution
│   ├── tool_base.py     # Base classes for tool modules
│   └── urls.py          # URL constants and helpers
├── cli/
│   ├── main.py          # Top-level parser, dispatch
│   ├── common.py        # Shared CLI utilities
│   ├── formatter.py     # Custom help formatter
│   ├── project_config.py # Project-level config helpers
│   ├── run/             # Run subcommands
│   │   ├── agent.py     # Agent launcher with registry
│   │   ├── proxy.py     # Proxy management
│   │   └── tools.py     # Unified tool management
│   ├── setup/           # Setup subcommands
│   │   ├── recipe.py    # Recipe init (re-exports from recipe/)
│   │   ├── config.py    # Config dispatcher (CLI parser)
│   │   └── deinit.py    # Teardown
│   ├── manage/          # Manage subcommands
│   │   ├── doctor.py    # Environment validation
│   │   ├── update.py    # Update checker
│   │   └── admin/       # Backup/restore
│   ├── git/             # Git workflows
│   │   ├── commit.py    # LLM-powered commit
│   │   ├── pr.py        # LLM-powered PR
│   │   ├── config.py    # Git config helpers
│   │   ├── git_ops.py   # Git operations
│   │   ├── llm.py       # LLM integration for git
│   │   └── templates.py # Commit/PR templates
│   ├── vscode.py        # VS Code agent config generation
│   └── docker_utils.py  # Docker primitives (re-exported via core/container.py)
├── docker/
│   ├── client.py        # Docker API client wrapper
│   └── pull.py          # Image pull, digest comparison
├── tools/
│   ├── registry.py      # Reference-counted tool lifecycle
│   ├── chrome.py        # Chrome tool
│   ├── web.py           # Web tool
│   ├── github.py        # GitHub MCP tool
│   ├── web_bridge.py    # Web bridge tool
│   └── schemas/         # Per-tool Pydantic schemas
├── agents/
│   └── vscode/          # VS Code config generation
├── admin/
│   ├── backup.py        # Backup engine
│   ├── restore.py       # Restore engine
│   ├── prune.py         # Old backup removal
│   └── _utils.py        # Shared admin utilities
├── recipe/
│   ├── store.py         # Recipe store management
│   ├── merge.py         # Recipe merging logic
│   ├── plan.py          # Recipe planning
│   ├── apply.py         # Recipe application
│   ├── generated_artifacts.py # Setup script generation
│   └── materialize.py   # Recipe file materialization
└── schemas/
    └── profiles.py      # Profile schema definitions
```

## 2. Shared Utilities

### `eprint()`

Defined once in `log.py`. All modules import from there:

```python
from codefreedom.log import eprint
```

**Do not** duplicate `eprint()` in other modules.

### `tag()`

Defined in `log.py`. Use for colored CLI output:

```python
from codefreedom.log import tag
eprint(f"{tag('OK')} Operation completed.")
```

**Do not** use bare `[TAG]` strings.

### `_VAR_REF_RE` Regex

Defined once in `config/interpolation.py`. All modules import from there:

```python
from codefreedom.config.interpolation import _VAR_REF_RE
```

**Do not** duplicate this regex in other modules.

### `resolve_var()` / `resolve_dict()` / `interpolate_all()`

Defined in `config/interpolation.py`. Use these for all `${VAR}` resolution:

```python
from codefreedom.config.interpolation import resolve_var, resolve_dict, interpolate_all
```

**Do not** inline regex substitution in other modules.

### `load_config()`

Single entry point for all configuration. Defined in `config/loader.py`:

```python
from codefreedom.config import load_config
```

**Do not** read YAML files directly -- always go through `load_config()`.

## 3. Tool Module Pattern

All tool modules (chrome, web, github, web_bridge) follow the same structure:

```python
# 1. Defaults
_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:<tool>-latest"
_DEFAULT_CONTAINER_NAME = "codefreedom-<tool>"
_DEFAULT_PORT = <port>

# 2. Profile loader
def _load_profile() -> dict:
    settings = { ... }
    return load_tool_profile(...)

# 3. Init redirect
def init_tool() -> int:
    return init_tool_redirect("<tool>.yaml")

# 4. Actions: start, stop, restart, status
def start(settings: dict) -> int: ...
def stop(settings: dict) -> int: ...
def restart(settings: dict) -> int: ...
def status(settings: dict) -> int: ...

# 5. Entry point
def run(args: argparse.Namespace) -> int: ...
```

## 4. Argument Access

Use `getattr(args, 'field', default)` for optional arguments:

```python
# Good
profile_name = getattr(args, "profile", None) or "default"
force = getattr(args, "force", False)

# Bad -- may raise AttributeError
profile_name = args.profile  # if not always set
```

## 5. Docker Container Lifecycle

Use shared helpers from `core/container.py` (canonical facade):

| Helper | Purpose |
|---|---|
| `container_is_running(name)` | Check if running |
| `container_exists(name)` | Check if exists |
| `start_tool_init_gate(profile, tool)` | Pre-start validation |
| `start_tool_remove_stopped(name, label)` | Clean up old container |
| `start_tool_ensure_image(settings, label)` | Verify/pull image |
| `start_tool_docker_guard(label)` | Check Docker available |
| `stop_tool_container(settings, label)` | Stop and remove |
| `load_tool_profile(...)` | Load YAML profile with defaults |

These are re-exported from `cli/docker_utils.py` via the `core/container.py` facade.
Tool modules should import from `core/container.py`, not directly from `cli/docker_utils.py`.

## 6. Type Annotations

- Use `dict` (not `Dict`) for modern Python 3.10+ style.
- Use `str | None` (not `Optional[str]`) for modern union types.
- Use `list[str]` (not `List[str]`) for modern generic syntax.

## 7. Testing

- All tests use `tmp_path` fixtures and `monkeypatch` for path isolation.
- Never touch real `~/.codefreedom/` during tests.
- Test files mirror source structure: `tests/test_<module>.py`.
- Run tests: `python -m pytest tests/ -v`
