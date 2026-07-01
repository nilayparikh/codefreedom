# CodeFreedom — AGENTS.md

> Conventions, acceptance criteria, and verification commands for all contributors (human and AI).

## Project Overview

CodeFreedom is a CLI (`cf`) that sits between you and your code agent (Claude Code, MiMoCode, OpenCode). It provides:

- **LLM proxy routing** via a self-hosted LiteLLM image (embedded PostgreSQL, multi-provider)
- **Profile management** — model switching, env inheritance, tool declarations
- **Browser tools** — Chrome (CDP + MCP), Camoufox stealth browser, GitHub MCP, Web Bridge
- **Recipe system** — pre-built config bundles that wire up proxy, profiles, and providers in one command

**Python 3.10+** · **Apache 2.0** · Entry points: `codefreedom` / `cf`

## Development Setup

```bash
python3 -m venv .venv                # create venv (first time only)
source .venv/bin/activate            # activate venv
pip install -e ".[dev]"              # editable install with dev deps
python -m codefreedom --help         # verify CLI works
```

> **CRITICAL: Python Environment Rule**
> ALL Python operations (pip install, pytest, mypy, ruff, git-cliff, etc.)
> MUST use the project's `.venv`. Never install into system Python or
> use `--break-system-packages`. Commands must be prefixed with
> `.venv/bin/` or run after `source .venv/bin/activate`.
>
> Bad:  `pip install git-cliff`
> Bad:  `pip install --break-system-packages git-cliff`
> Good: `.venv/bin/pip install git-cliff`
> Good: `source .venv/bin/activate && pip install git-cliff`

## Verification Commands

Run these before every commit. All must pass (use `.venv/bin/` prefix or ensure venv is active).

```bash
# 1. Unit tests (fast, ~2s)
.venv/bin/pytest tests/ -m unit -q --tb=short

# 2. Full test suite
.venv/bin/pytest tests/ -q --tb=short

# 3. Lint
.venv/bin/ruff check src/ tests/

# 4. Type-check
.venv/bin/mypy src/ --ignore-missing-imports
```

### When Modifying a Module

| What Changed | Command |
|---|---|
| Pure logic | `pytest tests/test_<module>_helpers.py -q` |
| I/O code | `pytest tests/test_<module>_io.py -q` |
| CLI commands | `pytest tests/test_<module>_cmd.py -q` |

Always run the full suite before committing.

### Pre-Commit Hooks

The repo uses pre-commit. Hooks run automatically on `git commit`:

1. `markdownlint-cli2 --fix` — markdown formatting
2. `ruff check src/ tests/ --fix` — lint + auto-fix
3. `mypy src/ --ignore-missing-imports` — type-check
4. `pytest tests/ -v --tb=short` — full test suite
5. `mkdocs build --strict` — docs build (only if pages/ changed)

## Acceptance Criteria for Any Code Change

1. **Unit tests pass** — `pytest tests/ -m unit -q --tb=short`
2. **Full suite passes** — `pytest tests/ -q --tb=short`
3. **Lint clean** — `ruff check src/ tests/`
4. **Types clean** — `mypy src/ --ignore-missing-imports`
5. **No regressions** — existing tests still pass
6. **Style matches** — follow existing patterns in the file you're editing

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full component inventory and dependency graph.

### Layer Model

```text
User (CLI)
  |
cli/          -- command dispatch, user-facing logic
  |
config/       -- YAML loading, ${VAR} interpolation, schema validation, runtime settings
core/         -- env helpers, container lifecycle, agent runtime, HTTP client, proxy env, tool base
  |
docker/       -- Docker client helpers, image pull utilities
tools/        -- tool classes, MCP endpoint dispatch
  |
recipe/       -- recipe store, plan, merge, apply
admin/        -- backup, restore, prune
```

Each layer calls only the layer below it. No cross-layer or sideways calls.

### Entry Points

| Entry Point | Module |
|---|---|
| `cf` / `codefreedom` | `src/codefreedom/cli/main.py:main` |
| `python -m codefreedom` | `src/codefreedom/__main__.py` |

### CLI Command Structure

```text
cf setup    (s)   init (i) | config (c) | deinit (di)
cf run      (r)   agent (ag) | proxy (px) | tools (tl)
cf manage   (m)   doctor (dr) | update (up) | admin (adm)
cf git      (g)   commit (c) | pr (p)
```

### Registered Agents

| Agent | Alias | Module |
|---|---|---|
| `claude-code` | `cc` | `cli/claude.py` |
| `mimo-code` | `mc` | `cli/mimo.py` |
| `open-code` | `oc` | `cli/opencode.py` |
| `pi-code` | `pc` | `cli/pi.py` |
| `codex-code` | `cx` | `cli/codex.py` |

## Code Conventions

### General Style

- **Python 3.10+** — use `dict`, `list[str]`, `str | None` (not `Dict`, `List`, `Optional`)
- **4-space indentation** for Python (see `.editorconfig`)
- **LF line endings**, UTF-8 charset
- **No comments** unless explicitly asked — code should be self-documenting
- **One responsibility per file** — if a file does two things, split it
- **Add a module when shared across 2+ locations** — one-off logic stays inline

### Imports

- Use `from __future__ import annotations` at the top of every module
- Import from the canonical source — never duplicate utilities

### Shared Utilities -- Single Source of Truth

| Utility | Defined In | Import From |
|---|---|---|
| `eprint()` | `log.py` | `from codefreedom.log import eprint` |
| `tag()` | `log.py` | `from codefreedom.log import tag` |
| `_VAR_REF_RE` | `config/interpolation.py` | `from codefreedom.config.interpolation import _VAR_REF_RE` |
| `resolve_var()` / `resolve_dict()` / `interpolate_all()` | `config/interpolation.py` | `from codefreedom.config.interpolation import ...` |
| `ConfigError` | `config/errors.py` | `from codefreedom.config.errors import ConfigError` |
| `ProfileError` | `config/errors.py` | `from codefreedom.config.errors import ProfileError` |
| YAML loading | `config/yaml_utils.py` | `from codefreedom.config.yaml_utils import safe_load` |
| `get_codefreedom_dir()` | `core/config.py` | `from codefreedom.core.config import get_codefreedom_dir` |
| Proxy URL detection | `core/agent_runtime.py` | `from codefreedom.core.agent_runtime import detect_proxy_url` |
| Proxy model fetch | `core/agent_runtime.py` | `from codefreedom.core.agent_runtime import fetch_proxy_models` |
| Provider model building | `core/agent_runtime.py` | `from codefreedom.core.agent_runtime import build_provider_models` |
| Container lifecycle | `core/container.py` | `from codefreedom.core.container import ...` |
| Docker digest helpers | `docker/pull.py` | `from codefreedom.docker.pull import normalize_ref, parse_image_ref, get_local_digest` |
| `resolve_agent_runtime()` | `config/runtime.py` | `from codefreedom.config.runtime import resolve_agent_runtime` |
| `list_profiles()` | `config/runtime.py` | `from codefreedom.config.runtime import list_profiles` |
| `load_config()` | `config/loader.py` | `from codefreedom.config import load_config` |

**Do not duplicate** any of these in other modules.

### CLI Output Conventions

All `eprint()` messages must use `tag('TAG')` from `codefreedom.log`. Bare `[TAG]` strings are forbidden.

#### Tag Color Map

| Color | Tags |
|---|---|
| **Green** | `OK`, `SET`, `SAME`, `CREATE`, `MKDIR`, `BACKUP`, `PRUNE`, `KEEP` |
| **Yellow** | `WARN`, `SKIP`, `DEINIT`, `ADMIN`, `DELETE` |
| **Red** (bold) | `FAIL`, `MISSING`, `ERROR` |
| **Cyan** | `PLAN`, `SECRETS`, `RECIPE`, `STORE`, `PROXY`, `RESTORE`, `VSCODE`, `TOOLS`, `AGENT`, `DOCTOR`, `SANDBOX`, `MCP`, `FETCH`, `INFO`, `ENV`, `GPU`, `IMAGE`, `CONTAINER`, `NATIVE`, `CONFIG`, `LOCAL`, `COMMIT`, `PUSH`, `LSP`, `LEAN-CTX`, `CODEX`, `PI`, `CHROME`, `CLEAN`, `EXEC`, `GITHUB`, `INIT`, `MIMO`, `OPENCODE`, `PROFILE`, `PROFILES`, `RUN`, `UPDATE`, `WEB`, `WEB-BRIDGE` |
| **Dim** | Any tag not in the above sets |

#### Output Streams

| Stream | Use For | Function |
|---|---|---|
| **stderr** | Status, progress, warnings, errors | `eprint()` |
| **stdout** | Machine-readable output only (URLs, config fragments, list data) | `print()` |

#### Message Format

```text
[COMPONENT] Action completed.
[COMPONENT] Using data dir: /path/to/dir.
```

- All messages end with a period
- Continuation lines use 3-space indent
- `[ERROR]` prefix for fatal errors (return code 1)
- `Warning:` text within the component prefix for non-fatal issues

#### Component Prefixes

| Component | Prefix |
|---|---|
| Chrome tool | `[CHROME]` |
| Web tool | `[WEB]` |
| GitHub MCP | `[GITHUB]` |
| Web bridge | `[WEB-BRIDGE]` |
| Tools manager | `[TOOLS]` |
| Proxy | `[PROXY]` |
| Admin/backup | `[ADMIN]` |
| Deinit | `[DEINIT]` |
| Doctor | `[DOCTOR]` |
| Recipe | `[RECIPE]` |
| Update | `[UPDATE]` |
| VS Code | `[VSCODE]` |
| Environment loader | `[ENV]` |
| Profile loader | `[PROFILE]` |
| MCP | `[MCP]` |

### Argument Access

Use `getattr(args, 'field', default)` for optional arguments:

```python
# Good
profile_name = getattr(args, "profile", None) or "default"
force = getattr(args, "force", False)

# Bad — may raise AttributeError
profile_name = args.profile  # if not always set
```

### Type Annotations

- `dict` not `Dict`
- `str | None` not `Optional[str]`
- `list[str]` not `List[str]`

## Testing

### Test Architecture

Tests are split into **unit** (pure logic, ~2s) and **integration** (I/O, Docker, ~10s).

| Category | Marker | Content |
|---|---|---|
| **Unit** | `@pytest.mark.unit` | Pure functions, transforms, parsers, validation |
| **Integration** | `@pytest.mark.integration` | I/O, Docker, subprocess, network, CLI commands |

### Decision Rule

#### "Does this test read/write files, call subprocess, or make network requests (even mocked)?"

- **Yes** → integration
- **No** → unit

If a test uses `tmp_path` for filesystem assertions (not just as a throwaway), it's integration. If `tmp_path` is only used to set `CODEFREEDOM_HOME` for env-var resolution, it's unit.

### Test File Naming

| Pattern | Type |
|---|---|
| `test_<module>_helpers.py` | Unit tests (pure logic) |
| `test_<module>_io.py` | Integration tests (I/O, filesystem) |
| `test_<module>_cmd.py` | Integration tests (CLI commands) |
| `test_<module>.py` | Single-responsibility module |

### Conventions

- All tests use `tmp_path` fixtures and `monkeypatch` for isolation
- Never touch real `~/.codefreedom/` during tests
- `conftest.py` sets `CODEFREEDOM_HOME` to a function-scoped `tmp_path`
- Test files use `pytestmark = pytest.mark.unit` or `pytest.mark.integration` at module level
- Private functions (`_prefix`) are tested directly — this is intentional
- Mock at the lowest boundary: mock `_do_get` for HTTP tests, not `get_json`

### Running Tests

```bash
# All tests
pytest tests/ -q

# Unit only (~2s)
pytest tests/ -m unit -q

# Integration only (~10s)
pytest tests/ -m integration -q

# Specific file
pytest tests/test_recipe_merge.py -q

# Specific class
pytest tests/test_admin_helpers.py::TestCategorize -q
```

### Adding New Tests

1. Determine unit vs integration (see Decision Rule)
2. Place in the appropriate file or create one following the naming convention
3. Add `pytestmark` if creating a new file
4. Run `pytest tests/ -m unit -q` for unit or `pytest tests/ -m integration -q` for integration
5. Ensure no regressions: `pytest tests/ -q --tb=short`

## Key Patterns

### Profile Inheritance

- `default` and `bare` are **standalone** — no inheritance
- All other profiles inherit from `default`
- Mode-specific overrides (`local.env`) also inherit
- `tools` field declares tool containers to auto-start

### Environment Variable Chain

Priority (lowest to highest):

1. `profiles.yaml` — recipe-managed defaults with `${VAR:-default}`
2. `recipe.yaml` — recipe vars (override profiles)
3. `override.yaml` — user overrides (same schema)
4. `.cf.yaml` — per-folder override (same schema, explicit path; see below)
5. `CF_CLI_*` — secrets from machine env (prefix stripped, highest priority)

All layers support `${VAR}` and `${VAR:-default}` interpolation. Empty-string values in `CF_CLI_*` are valid overrides (do NOT fall through to default). No `.env` files are read — all configuration comes from YAML + `CF_CLI_*` env vars. Proxy-related env vars use the `PROXY_*` / `CF_CLI_PROXY_*` naming; older `LITELLM_*` names are not the canonical CodeFreedom config surface.

**Per-folder `.cf.yaml`:** Use `cf s folder <path>` (alias `cf s f`) to copy the current `override.yaml` into `<path>/.cf.yaml`. The file is the same schema as `override.yaml` and sits one layer above it. Activate it by exporting `CF_CLI_CF_YAML=<path>` (or by passing `cf_yaml_path=` to `load_config()`). Existing `.cf.yaml` files are not overwritten by default — pass `--force` to override. The git module's existing block-schema `.cf.yaml` (`git:` block) is unaffected: it lives in a different top-level key and is read by `cli/git/config.py`, not by `load_config`.

**Bind address:** Configure via `common.bind_address` in `override.yaml` or `CF_CLI_BIND_ADDRESS` env var. Default: `0.0.0.0` (all interfaces, remote-accessible).

**Remote URL:** Configure per-component in `override.yaml`:

- `proxy.remote_url` — clients use remote proxy instead of local
- `tools.<tool>.remote_url` — MCP endpoints use remote tool URL

### Tool Module Pattern

All tool modules (chrome, web, github, web_bridge) follow this structure:

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

### Docker Container Lifecycle

Use shared helpers from `core/container.py`:

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

### Tool Registry — Reference Counting

Tools are shared infrastructure. First session starts them, last session stops them.

| Session A | Session B | Chrome State |
|---|---|---|
| starts | — | started (ref=1) |
| running | starts | already running (ref=2) |
| exits | running | stays running (ref=1) |
| — | exits | stopped (ref=0) |

### Version Source of Truth

`version.yaml` is the single source of truth for versioning. It holds the base version, dev iteration, and RC number. `pyproject.toml` is derived at release time by CI workflows and should never be edited on branches. `__init__.py` derives `__version__` from `importlib.metadata`.

## Docker Images

| Image | Dockerfile | Use Case |
|---|---|---|
| Chrome | `docker/chrome/Dockerfile.Chrome` | Headless Chromium |
| Web | `docker/web/Dockerfile.Web` | Camoufox MCP |
| GitHub MCP | `docker/github/Dockerfile.Github` | GitHub API tools |
| Codebase Memory MCP | `docker/codebase-memory/Dockerfile.Codebase-memory` | Local code knowledge graph (14 MCP tools) |
| LiteLLM | `docker/litellm/Dockerfile.LitellmFinal` | LLM proxy + PG |
| LiteLLM Base | `docker/litellm/Dockerfile.LitellmBase` | LiteLLM base image |
| PG Base | `docker/litellm/Dockerfile.PgBase` | PostgreSQL base image |
| Web Bridge | `docker/web-bridge/Dockerfile.Bridge` | SearXNG bridge |

Docker tags must be **lowercase**.

## Gotchas

### `--dangerously-skip-permissions`

Only pass this if the user explicitly requests it.

### Unicode breaks Windows CI

**Always use plain ASCII in user-facing strings.** Windows cp1252 cannot encode Unicode box-drawing characters.

### Encoding on Windows

**Always pass `encoding="utf-8"` to `read_text()` and `write_text()`.** On Windows, the default encoding is `cp1252`, not UTF-8.

### Tool profiles use YAML — not JSON

Tool profiles use `.yaml` files. Legacy `.json` profiles for chrome/web are still supported.

### Proxy is Docker-only — no native mode

The proxy always runs via `docker compose`. No native Python path. Do not reintroduce native-mode logic.

### Remote components

Components (proxy and tools) can be configured as remote:

- **Proxy:** `proxy.remote_url` in `override.yaml` — clients use `PROXY_BASE_URL` from config instead of local detection.
- **Tools:** `tools.<tool>.remote_url` in `override.yaml` — MCP endpoints use the remote URL verbatim.
- **Bind address:** `common.bind_address` controls server-side bind (default `0.0.0.0`). Client-side URL stays `127.0.0.1` for local access.
- When remote, lifecycle commands (`start`/`stop`/`restart`) are refused — use `--local` to override.

### CustomLogger callbacks: reference `instance`, not the class

Always reference a module-level singleton instance from `config.yaml`, e.g. `plugins.reasoning_efforts_mapping.instance`.

### Patches are baked into the LiteLLM image

Patches in `docker/litellm/patches/` are applied during image build. If you change LiteLLM and a patch can no longer find its target, the build fails loudly.

### Bare agent names are invalid

CodeFreedom canonical names must be hyphenated: `claude-code`, `mimo-code`, `open-code`, `pi-code`, `codex-code`. Bare names (`claude`, `mimo`, `opencode`, `pi`, `codex`) fail in CLI dispatch.

### Recipe directories are independent copies

`_default`, `costeffective-coding`, `costeffective-coding-with-local` share structure but have independent files. Fix scripts in all 3. Never blindly copy `recipe.yaml` or provider configs.

### Tags must be CAPS with `tag()` helper

All `print()`/`eprint()` feedback must use `tag('TAG')` from `codefreedom.log`. Bare `[TAG]` strings violate the convention. See the tag color map above.

### `eprint` and `_VAR_REF_RE` -- single source of truth

`eprint()` is defined once in `log.py`. `_VAR_REF_RE` is defined once in `config/interpolation.py`. Do not duplicate these in other modules.

## CI/CD

### Workflows

All CI is consolidated into `ci.yml`. No separate lint/test/type-check workflows.

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci.yml` | Push to ANY branch + PRs | Lint, type-check, unit tests, integration tests |
| `publish-dev.yml` | workflow_dispatch | Build + publish dev version to PyPI (dev/v* only) |
| `publish-rc.yml` | workflow_dispatch | Build + publish RC version to PyPI (rc/v* only) |
| `pipy.yaml` | workflow_dispatch | Build + publish final version to PyPI + GitHub Release |
| `docker-*.yml` | workflow_dispatch | Build + publish Docker images |
| `trivy.yml` | Various | Security scanning |
| `publish-docs.yml` | Various | MkDocs deployment |

### CI Stages (all in ci.yml)

1. **Lint** — `ruff check src/ tests/`
2. **Type-check** — `mypy src/ --ignore-missing-imports`
3. **Unit tests** — `pytest tests/ -v --tb=short` (Python 3.10/3.11/3.12)
4. **Integration tests** — build wheel, install, smoke test (Ubuntu/Windows/macOS)

### Branch Protection & Promotion Flow

**CRITICAL: NEVER push directly to protected branches (main, prerelease/v*, release/v*).**

Branch protection requires PRs and status checks. Direct pushes will be rejected.

**Required promotion flow:**

```text
feature/* -> PR to prerelease/v* -> PR to release/v* -> PR to main
```

Steps:

1. Create feature branch: `git checkout -b feature/your-feature`
2. Commit changes on feature branch
3. Push feature branch: `git push -u origin feature/your-feature`
4. Create PR: feature -> prerelease/v*
5. Wait for CI checks to pass, merge PR
6. Create PR: prerelease/v* -> release/v*
7. Wait for CI checks to pass, merge PR
8. Create PR: release/v* -> main
9. Wait for CI checks to pass, merge PR

### Release Process

Releases are triggered via GitHub Actions `workflow_dispatch` — no local scripts needed.

**Version is derived from `version.yaml`. `pyproject.toml` is NEVER modified on branches.**

**Version format:**

- **Dev**: `{version}rc{rc}.dev{dev}` (e.g., `0.2.2rc1.dev1`) -- from `prerelease/v*` branches
- **RC**: `{version}rc{rc}` (e.g., `0.2.2rc1`) -- from `release/v*` branches
- **Final**: `{version}` (e.g., `0.2.2`) -- tag on `main`

**Promotion steps:**

1. Ensure changes are promoted to desired branch (see promotion flow above)
2. For dev releases: Go to **Actions -> Publish Dev -> Run workflow** (must be on `prerelease/v*`)
3. For RC releases: Go to **Actions -> Publish RC -> Run workflow** (must be on `release/v*`)
4. For final releases: Run `python scripts/release.py` on `main` to create tag, then `pipy.yaml` publishes

**After final release:** `release.py` auto-increments `version` patch and resets `rc`/`dev` counters.

**For next RC cycle:** Run `python scripts/release.py --bump-rc` to increment `rc` and reset `dev`.

### Documentation

```bash
mkdocs serve -a localhost:8080  # local docs preview
```

## Recipes

Recipes are config bundles from `github.com/nilayparikh/codefreedom-recipes`.

| Recipe | Description |
|---|---|
| `costeffective-coding` | Cloud providers only (Azure, OpenCode, OpenRouter, DeepSeek) |
| `costeffective-coding-with-local` | Cloud + local inference (vLLM, Ollama, etc.) |

Both recipes extend `_default` (base config with shared tool profiles, proxy config, plugins). `_default` is not directly visible to users — it is applied automatically as a base layer.

Apply with: `cf s i install <recipe-name>` (or `cf s i <recipe-name>`)

## MCP Servers

Configured in `.mcp.json`. Endpoints use `127.0.0.1` for local access. For remote access, configure `remote_url` per-tool:

| Server | Endpoint | Remote Config |
|---|---|---|
| Chrome DevTools | `http://127.0.0.1:9223/mcp` | `tools.chrome.remote_url` |
| Web (Camoufox) | `http://127.0.0.1:8420/mcp` | `tools.web.remote_url` |
| GitHub | `http://127.0.0.1:8129/mcp` | `tools.github.remote_url` |
| Codebase Memory | `http://127.0.0.1:8330/mcp` | `tools.codebase_memory.remote_url` |

## Internal Specs

| Document | Purpose |
|---|---|
| `docs/cli-reference.md` | Complete CLI command reference |
| `docs/cli-output.md` | CLI output conventions |
| `docs/code-style.md` | Code style and patterns |
| `docs/patterns.md` | Key patterns (profiles, env chain, tools) |
| `docs/docker.md` | Docker images and naming |
| `docs/ci-cd.md` | CI/CD workflows |
| `docs/tests.md` | Test coverage and architecture |
