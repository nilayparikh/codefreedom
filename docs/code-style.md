# Code Style Standards

Internal coding conventions for the CodeFreedom CLI project.

## 1. Module Organization

```text
src/codefreedom/
├── __init__.py          # __version__ from importlib.metadata
├── __main__.py          # python -m entry point
├── env_loader.py        # .env chain loading, eprint(), get_env()
├── log.py               # tag() colored output helper
├── launcher.py          # Docker sandbox and native local execution
├── cli/
│   ├── main.py          # Top-level parser, dispatch
│   ├── common.py        # Shared CLI utilities
│   ├── formatter.py     # Custom help formatter
│   ├── run/             # Run subcommands
│   │   ├── agent.py     # Agent launcher with registry
│   │   ├── proxy.py     # Proxy management
│   │   └── tools.py     # Unified tool management
│   ├── setup/           # Setup subcommands
│   │   ├── init.py      # Recipe initialization
│   │   ├── config.py    # Unified config dispatcher
│   │   └── deinit.py    # Teardown
│   ├── manage/          # Manage subcommands
│   │   ├── doctor.py    # Environment validation
│   │   ├── update.py    # Update checker
│   │   └── admin/       # Backup/restore
│   └── git/             # Git operations
├── core/
│   ├── config.py        # CODEFREEDOM_HOME resolution
│   ├── interpolate.py   # ${VAR} interpolation (shared regex)
│   └── profiles.py      # Profile YAML loading, inheritance
├── sandbox/
│   └── launcher.py      # Container lifecycle management
├── docker/
│   └── utils.py         # Shared Docker helpers
├── tools/
│   ├── registry.py      # Reference-counted tool lifecycle
│   ├── chrome.py        # Chrome tool
│   ├── web.py           # Web tool
│   ├── github.py        # GitHub MCP tool
│   └── web_bridge.py    # Web bridge tool
├── agents/
│   └── ...              # Agent-specific modules
├── admin/
│   ├── backup.py        # Backup engine
│   ├── restore.py       # Restore engine
│   └── _utils.py        # Shared admin utilities
├── recipe/
│   ├── store.py         # Recipe store management
│   ├── merge.py         # Recipe merging logic
│   ├── plan.py          # Recipe planning
│   └── apply.py         # Recipe application
└── schemas/
    └── profiles.py      # Pydantic validation models
```

## 2. Shared Utilities

### `eprint()`

Defined once in `env_loader.py`. All modules import from there:

```python
from codefreedom.env_loader import eprint
```

**Do not** duplicate `eprint()` in other modules.

### `_VAR_REF_RE` Regex

Defined once in `core/interpolate.py`. All modules import from there:

```python
from codefreedom.core.interpolate import _VAR_REF_RE
```

**Do not** duplicate this regex in other modules.

### `resolve_env_vars()` / `resolve_env_dict()`

Defined in `core/interpolate.py`. Use these for all `${VAR}` resolution:

```python
from codefreedom.core.interpolate import resolve_env_vars, resolve_env_dict
```

**Do not** inline regex substitution in other modules.

### `tag()`

Defined in `log.py`. Use for colored CLI output:

```python
from codefreedom.log import tag
eprint(f"{tag('OK')} Operation completed.")
```

**Do not** use bare `[TAG]` strings.

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

Use shared helpers from `docker/utils.py`:

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

## 6. Type Annotations

- Use `dict` (not `Dict`) for modern Python 3.10+ style.
- Use `str | None` (not `Optional[str]`) for modern union types.
- Use `list[str]` (not `List[str]`) for modern generic syntax.

## 7. Testing

- All tests use `tmp_path` fixtures and `monkeypatch` for path isolation.
- Never touch real `~/.codefreedom/` during tests.
- Test files mirror source structure: `tests/test_<module>.py`.
- Run tests: `python -m pytest tests/ -v`
