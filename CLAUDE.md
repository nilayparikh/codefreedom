# CodeFreedom — CLAUDE.md

> Unified CLI wrapper for code agents. Switch LLM providers, isolate environments, eliminate config sprawl.

## Project Purpose

CodeFreedom solves three problems:

1. **Model lock-in** — switch LLM providers without reconfiguring your code agent.
2. **Environment chaos** — isolated, reproducible environments per project with GPU support.
3. **Config sprawl** — profiles, proxy routing, and sandbox settings managed from one place (`~/.codefreedom`).

## Behavioral Guidelines

- **Think before coding.** State assumptions. Ask if uncertain. Surface tradeoffs.
- **Simplicity first.** Minimum code that solves the problem. No speculative features or abstractions.
- **Surgical changes.** Touch only what's needed. Match existing style. Clean up only your own mess.
- **Goal-driven.** Define verifiable success criteria. Loop until tests pass.

## Quick Start

```bash
pip install -e ".[dev]"              # editable install with dev deps
python -m pytest tests/ -v           # run all tests
python -m pytest tests/ -m unit -v   # unit tests only (~2s)
ruff check src/ tests/               # lint
mypy src/ --ignore-missing-imports   # type-check
python -m codefreedom --help         # CLI (no install needed)
```

## Architecture

```text
src/codefreedom/
├── __init__.py              # __version__ from importlib.metadata
├── __main__.py              # python -m codefreedom entry point
├── env_loader.py            # .env chain, eprint()
├── log.py                   # tag(), colored output
├── launcher.py              # Agent-specific Docker orchestration
├── core/
│   ├── config.py            # CODEFREEDOM_HOME, resolve_agent_config()
│   ├── profiles.py          # load_profile_env(), tool profile resolution
│   ├── interpolate.py       # ${VAR} interpolation
│   └── http_client.py       # Shared HTTP utilities
├── cli/
│   ├── main.py              # Top-level parser: setup/run/manage
│   ├── common.py            # Shared CLI utilities
│   ├── formatter.py         # Help text formatting
│   ├── docker_utils.py      # start_tool_container(), image checks
│   ├── claude.py            # cf run agent claude-code
│   ├── mimo.py              # cf run agent mimo-code
│   ├── opencode.py          # cf run agent open-code
│   ├── vscode.py            # VS Code config helpers
│   ├── run/
│   │   ├── agent.py         # Agent dispatch: alias resolution, validate_agent_args()
│   │   ├── proxy.py         # cf run proxy: Docker Compose lifecycle
│   │   └── tools.py         # cf run tools: delegates to tools/registry
│   ├── setup/
│   │   ├── recipe.py        # cf setup init: plan/apply recipes
│   │   ├── config.py        # cf setup config vscode
│   │   └── deinit.py        # cf setup deinit
│   └── manage/
│       ├── doctor.py        # cf manage doctor: env checks, agent binary checks
│       ├── update.py        # cf manage update: image/PyPI checks
│       └── admin.py         # cf manage admin: backup/restore/prune/inspect
├── sandbox/
│   ├── launcher.py          # run_sandbox(), sandbox_status(), sandbox_stop()
│   ├── signals.py           # Signal forwarding
│   └── terminal.py          # Terminal allocation
├── tools/
│   ├── registry.py          # acquire_tools(), release_tools(), start_all_tools()
│   ├── chrome.py            # Chrome MCP tool
│   ├── web.py               # Camoufox MCP tool
│   ├── web_bridge.py        # Web bridge tool
│   ├── github.py            # GitHub MCP tool
│   └── schemas/             # Per-tool Pydantic schemas
├── agents/
│   └── vscode/
│       ├── claude_settings.py  # Claude Code VS Code settings
│       └── proxy_models.py     # Proxy model list for VS Code
├── recipe/
│   ├── store.py             # Git clone/update of recipe repository
│   ├── plan.py              # Recipe plan generation, secrets status
│   ├── merge.py             # File merge logic
│   └── apply.py             # _resolve_secret(), _print_summary(), apply
├── admin/
│   ├── backup.py            # Archive creation, PG dump
│   ├── restore.py           # Archive extraction, diff preview
│   ├── prune.py             # Old backup removal
│   └── _utils.py            # _MANAGED_PATHS, _collect_files(), _redact_value()
├── docker/
│   └── client.py            # Docker API client wrapper
└── schemas/
    ├── profiles.py          # Profile Pydantic models
    └── recipe.py            # Recipe Pydantic models
```

Entry points: `codefreedom` / `cf` → `src/codefreedom/cli/main.py:main`

## Internal Specs

Standards and reference docs in `/specs/`:

| Document | Purpose |
|----------|---------|
| `specs/cli-reference.md` | Complete CLI command reference |
| `specs/cli-output.md` | CLI output conventions |
| `specs/code-style.md` | Code style and patterns |
| `specs/patterns.md` | Key patterns (profiles, env chain, tools) |
| `specs/docker.md` | Docker images and naming |
| `specs/ci-cd.md` | CI/CD workflows |
| `specs/tests.md` | Test coverage |

Full conventions, acceptance criteria, and verification commands → **AGENTS.md**

## Test Architecture

Tests are split into **unit** (pure logic, ~2s) and **integration** (I/O, Docker, ~10s). See `specs/tests.md` for full architecture.

**Acceptance criteria for any code change:**

```bash
# Required — unit tests must pass (fast feedback)
pytest tests/ -m unit -q --tb=short

# Required — full suite must pass
pytest tests/ -q --tb=short

# Required — lint and type-check
ruff check src/ tests/ && mypy src/ --ignore-missing-imports
```

**When modifying a module:**

- If you changed pure logic → run `pytest tests/test_<module>_helpers.py -q`
- If you changed I/O code → run `pytest tests/test_<module>_io.py -q`
- If you changed CLI commands → run `pytest tests/test_<module>_cmd.py -q`
- Always run the full suite before committing

**Test file naming:**

- `test_<module>_helpers.py` — unit tests (pure logic)
- `test_<module>_io.py` — integration tests (I/O, filesystem)
- `test_<module>_cmd.py` — integration tests (CLI commands)

## Gotchas

### `eprint` and `_VAR_REF_RE` — single source of truth

`eprint()` is defined once in `env_loader.py`. `_VAR_REF_RE` is defined once in `core/interpolate.py`. Do not duplicate these in other modules.

### `--dangerously-skip-permissions`

Sandbox mode **always** passes this to Claude CLI inside the container. Local mode only passes it if the user explicitly requests it.

### Unicode breaks Windows CI

**Always use plain ASCII in user-facing strings.** Windows cp1252 cannot encode Unicode box-drawing characters.

### Encoding on Windows

**Always pass `encoding="utf-8"` to `read_text()` and `write_text()`.** On Windows, the default encoding is `cp1252`, not UTF-8.

### Tool profiles use YAML — not JSON

Tool profiles use `.yaml` files. Legacy `.json` profiles for chrome/web are still supported.

### Proxy is Docker-only — no native mode

The proxy always runs via `docker compose`. No native Python path. Do not reintroduce native-mode logic.

### CustomLogger callbacks: reference `instance`, not the class

Always reference a module-level singleton instance from `config.yaml`, e.g. `plugins.reasoning_efforts_mapping.instance`.

### Patches are baked into the LiteLLM image

Patches in `docker/litellm/patches/` are applied during image build. If you change LiteLLM and a patch can no longer find its target, the build fails loudly.

### Bare agent names are invalid

`shutil.which("claude")` is correct — it looks up the actual binary on PATH. But CodeFreedom canonical names must be hyphenated: `claude-code`, `mimo-code`, `open-code`. Bare names (`claude`, `mimo`, `opencode`) fail in CLI dispatch.

### Recipe directories are independent copies

`_default`, `costeffective-coding`, `costeffective-coding-with-local` share structure but have independent files. Fix scripts in all 3. Never blindly copy `recipe.yaml` or provider configs.

### Tags must be CAPS with `tag()` helper

All `print()`/`eprint()` feedback must use `tag('TAG')` from `codefreedom.log`. Bare `[TAG]` strings violate the convention. See AGENTS.md for the full color map.
