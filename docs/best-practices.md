# Best Practices

> Canonical conventions for the CodeFreedom codebase. Every module must follow these.

## 1. File Header

Every `.py` file in `src/codefreedom/` **must** start with:

```python
"""One-line module description."""
from __future__ import annotations
```

- `from __future__ import annotations` is required (enables PEP 604 syntax on 3.10).
- Module docstring is required (one line, present tense).
- No license header (LICENSE + NOTICE at repo root is sufficient).
- No shebang line (only `scripts/` and `docker/` need them).

## 2. Imports

- **Always absolute:** `from codefreedom.config import load_config` — never relative (`from .loader import load_config`).
- **One canonical source per utility.** Never inline or reimplement what already exists:

    | Utility | Source |
    |---|---|
    | `eprint()` | `from codefreedom.log import eprint` |
    | `tag()` | `from codefreedom.log import tag` |
    | `load_config()` | `from codefreedom.config import load_config` |
    | `resolve_var()` / `resolve_dict()` / `interpolate_all()` | `from codefreedom.config.interpolation import ...` |
    | `_VAR_REF_RE` | `from codefreedom.config.interpolation import _VAR_REF_RE` |
    | `ConfigError` | `from codefreedom.config.errors import ConfigError` |
    | `ProfileError` | `from codefreedom.config.errors import ProfileError` |
    | YAML loading | `from codefreedom.config.yaml_utils import safe_load` |
    | `get_codefreedom_dir()` | `from codefreedom.core.config import get_codefreedom_dir` |
    | Proxy URL detection | `from codefreedom.core.agent_runtime import detect_proxy_url` |
    | Proxy model fetch | `from codefreedom.core.agent_runtime import fetch_proxy_models` |
    | Provider model building | `from codefreedom.core.agent_runtime import build_provider_models` |
    | Container lifecycle | `from codefreedom.core.container import ...` |
    | Docker digest helpers | `from codefreedom.docker.pull import normalize_ref, parse_image_ref, get_local_digest` |
    | `resolve_agent_runtime()` | `from codefreedom.config.runtime import resolve_agent_runtime` |
    | `list_profiles()` | `from codefreedom.config.runtime import list_profiles` |

- **No lazy imports inside function bodies** unless the import is heavy and only used in codepaths that may not execute (e.g., optional CLI subcommands).

## 3. CLI Output

- **stderr for status:** Use `eprint()` for all progress, warnings, errors.
- **stdout for data:** Use `print()` only for machine-readable output (URLs, config fragments, lists).
- **Always use `tag()`:** `eprint(f"{tag('OK')} Operation completed.")` — never bare `"[TAG]"` strings.
- **Messages end with a period.**
- **Tag color map:**

    | Color | Tags |
    |---|---|
    | Green | `OK`, `SET`, `SAME`, `CREATE`, `MKDIR`, `BACKUP`, `PRUNE`, `KEEP` |
    | Yellow | `WARN`, `SKIP`, `DEINIT`, `ADMIN`, `DELETE` |
    | Red (bold) | `FAIL`, `MISSING`, `ERROR` |
    | Cyan | `PLAN`, `SECRETS`, `RECIPE`, `STORE`, `PROXY`, `RESTORE`, `VSCODE`, `TOOLS`, `AGENT`, `DOCTOR`, `SANDBOX`, `MCP`, `FETCH`, `INFO`, `ENV`, `GPU`, `IMAGE`, `CONTAINER`, `NATIVE`, `CONFIG`, `LOCAL`, `COMMIT`, `PUSH`, `LSP`, `LEAN-CTX`, `CODEX`, `PI`, `CHROME`, `CLEAN`, `EXEC`, `GITHUB`, `INIT`, `MIMO`, `OPENCODE`, `PROFILE`, `PROFILES`, `RUN`, `UPDATE`, `WEB`, `WEB-BRIDGE` |
    | Dim | Any tag not in the above set |

- Tags not in the color map appear dim. If a tag deserves color, add it to `_TAG_CYAN` (or the appropriate set) in `log.py`.

## 4. Error Handling

- **Return exit codes:** CLI `run()` functions return `int` (0 = success, 1 = generic error, 2 = user error).
- **Raise for exceptional cases:** Use `ConfigError` / `MissingSecretError` from `config/errors.py` for config-related failures. Let the top-level dispatch catch them.
- **Error format:** `eprint(f"{tag('ERROR')} Human-readable message.")` + `return 1`.
- **Never print bare `[ERROR]`** — always use `tag('ERROR')` for ANSI color support.

## 5. Docstrings

- **Style:** Sphinx (reStructuredText) with `Args:`, `Returns:`, `Raises:` field lists.
- **Required on:** All public functions, all non-trivial private functions (3+ lines), all classes.
- **Not required on:** Trivial one-liner helpers.

```python
def load_config(config_dir: Path) -> ResolvedConfig:
    """Load and resolve all configuration from the given directory.

    Args:
        config_dir: Path to the ``.codefreedom/`` config directory.

    Returns:
        A fully resolved ``ResolvedConfig`` with all ``${VAR}``
        references interpolated.

    Raises:
        ConfigError: If required files are missing or malformed.
    """
```

## 6. Type Annotations

- `dict` not `Dict` — `def func() -> dict[str, str]:`
- `str | None` not `Optional[str]` — `def func(name: str | None = None):`
- `list[str]` not `List[str]` — `def func() -> list[str]:`
- `from __future__ import annotations` enables PEP 604 syntax at runtime (required).

## 7. Function Sizing

- **Hard limit:** 50 lines of executable code per function (not counting docstring/blanks).
- **Parameter limit:** 5 parameters max. At 6+, use a `@dataclass` or typed `TypedDict`.
- **Splitting:** Extract deeply-nested blocks into well-named private functions.
- **One responsibility per file.** If a file does two distinct things, split it.

## 8. Configuration & YAML

- **All YAML loading** goes through `codefreedom.config.yaml_utils.safe_load()`. No direct `import yaml` in business logic.
- **No `.env` files.** All config comes from YAML files + `CF_CLI_*` machine env vars.
- **Resolution chain** (lowest → highest priority): `profiles.yaml` → `recipe.yaml` → `override.yaml` → `CF_CLI_*`.
- **Interpolation happens at runtime** on every `load_config()` call. Files store literal `${VAR}` placeholders.
- **Bind address** is configured via `common.bind_address` in `override.yaml` or `CF_CLI_BIND_ADDRESS` env var. Default: `0.0.0.0` (all interfaces).
- **Remote URL** is configured per-component: `proxy.remote_url` or `tools.<tool>.remote_url` in `override.yaml`.

## 9. Agent Module Pattern

Every agent module (`mimo.py`, `opencode.py`, `codex.py`, `pi.py`) must:

1. Import shared proxy helpers from `codefreedom.core.agent_runtime` instead of defining `_detect_proxy_url()` / `_fetch_proxy_models()` / `_build_provider_models()` inline. Thin `_`-prefixed wrappers are acceptable for test compatibility.
2. Use `run_args = getattr(args, "agent", None)` pattern for optional args (not `args.agent`).
3. All `eprint()` output must use `tag()` — never bare `"[TAG]"` strings.

## 10. Tool Module Pattern

Every tool module (`chrome.py`, `web.py`, `github.py`, `web_bridge.py`) follows:

```python
_DEFAULT_IMAGE = "docker.io/nilayparikh/codefreedom:<tool>-latest"
_DEFAULT_CONTAINER_NAME = "codefreedom-<tool>"
_DEFAULT_PORT = <port>

def _load_profile() -> dict: ...
def init_tool() -> int: ...
def start(settings: dict) -> int: ...
def stop(settings: dict) -> int: ...
def restart(settings: dict) -> int: ...
def status(settings: dict) -> int: ...
def run(args: argparse.Namespace) -> int: ...
```

## 11. Testing

- **Every test file** must have a module-level `pytestmark`:

    ```python
    pytestmark = pytest.mark.unit   # or pytest.mark.integration
    ```

    Decision rule: "Does the test read/write files, call subprocess, or make network requests (even mocked)?" Yes → `integration`, No → `unit`.

- **Always prefer fixtures over manual setup:**
    - `tmp_path` over `tempfile.TemporaryDirectory`
    - `monkeypatch.setenv` over `os.environ["KEY"] = val` + manual cleanup
    - `capsys` over `StringIO` for stderr capture
- **Conftest:** Shared fixtures (`git_repo`) go in `tests/conftest.py`.
- **Shared helpers:** Reusable test functions (`write_tool_profile`, `clean_profiles`, `ToolRestartMixin`, `ToolRunDispatchMixin`) go in `tests/helpers.py`.
- **Isolation:** Never touch real `~/.codefreedom/` during tests. `conftest.py` sets `CODEFREEDOM_HOME` to `tmp_path`.
- **Naming:** `test_<module>_helpers.py` for unit, `test_<module>_io.py` for I/O, `test_<module>_cmd.py` for CLI.

## 12. Version Management

- Only `pyproject.toml` holds the version. `__init__.py` derives `__version__` from `importlib.metadata` — never edit it directly.

## 13. Git Workflow

```text
feature/* → PR to dev/v* → PR to rc/v* → PR to main
```

- No direct pushes to protected branches.
- PRs require status checks passing before merge.

## 14. Deprecation

- When a module is replaced, do **not** leave backward-compat re-export wrappers. Update all callers and delete the old module in a single PR.
- Exception: if the old module is part of a public API consumed externally, keep it for one release cycle with a clear `.. deprecated::` docstring.
