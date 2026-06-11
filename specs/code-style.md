# Code Style Standards

Internal coding conventions for the CodeFreedom CLI project.

## 1. Module Organization

```
src/codefreedom/
├── __init__.py          # __version__ from importlib.metadata
├── __main__.py          # python -m entry point
├── config.py            # CODEFREEDOM_HOME resolution
├── env_loader.py        # .env chain loading, eprint(), get_env()
├── interpolate.py       # ${VAR} interpolation (shared regex)
├── profiles.py          # Profile JSON/YAML loading, inheritance
├── tool_registry.py     # Reference-counted tool lifecycle
├── launcher.py          # Docker sandbox and native local execution
├── admin.py             # Backup/restore engine
├── cli/
│   ├── main.py          # Top-level parser, dispatch
│   ├── chrome.py        # Chrome tool subcommand
│   ├── web.py           # Web tool subcommand
│   ├── github.py        # GitHub MCP tool subcommand
│   ├── web_bridge.py    # Web bridge tool subcommand
│   ├── tools.py         # Unified tool management
│   ├── docker_utils.py  # Shared Docker helpers
│   ├── tool_init_utils.py # Shared init/acceptance prompts
│   └── ...              # Other subcommands
└── schemas/             # Pydantic validation models
```

## 2. Shared Utilities

### `eprint()`

Defined once in `env_loader.py`. All modules import from there:

```python
from codefreedom.env_loader import eprint
```

**Do not** duplicate `eprint()` in other modules. If a circular import would result, refactor the dependency instead.

### `_VAR_REF_RE` Regex

Defined once in `interpolate.py`. All modules import from there:

```python
from codefreedom.interpolate import _VAR_REF_RE
```

**Do not** duplicate this regex in `env_loader.py`, `profiles.py`, or any other module.

### `resolve_env_vars()` / `resolve_env_dict()`

Defined in `interpolate.py`. Use these for all `${VAR}` resolution:

```python
from codefreedom.interpolate import resolve_env_vars, resolve_env_dict
```

**Do not** inline regex substitution in `env_loader.py` or `profiles.py`. Use the shared functions.

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

# Bad — may raise AttributeError
profile_name = args.profile  # if not always set
```

## 5. Docker Container Lifecycle

Use shared helpers from `docker_utils.py`:

| Helper                                     | Purpose                              |
| ------------------------------------------ | ------------------------------------ |
| `container_is_running(name)`               | Check if running                     |
| `container_exists(name)`                   | Check if exists (running or stopped) |
| `start_tool_init_gate(profile, tool)`      | Pre-start validation                 |
| `start_tool_remove_stopped(name, label)`   | Clean up old container               |
| `start_tool_ensure_image(settings, label)` | Verify/pull image                    |
| `start_tool_docker_guard(label)`           | Check Docker available               |
| `stop_tool_container(settings, label)`     | Stop and remove                      |
| `restart_tool_container(settings, label)`  | Restart via docker                   |
| `load_tool_profile(...)`                   | Load YAML profile with defaults      |
| `resolve_data_dir(data_dir)`               | Resolve + create data directory      |

## 6. Port Checking

Use `is_port_available(port, host)` from `docker_utils.py` for checking specific ports. For finding a free port, use the pattern from `github.py` (`_find_free_port()`).

## 7. Type Annotations

- Use `dict` (not `Dict`) for modern Python 3.10+ style.
- Use `str | None` (not `Optional[str]`) for modern union types.
- Use `list[str]` (not `List[str]`) for modern generic syntax.

## 8. Testing

- All tests use `tmp_path` fixtures and `monkeypatch` for path isolation.
- Never touch real `~/.codefreedom/` during tests.
- Test files mirror source structure: `tests/test_<module>.py`.
