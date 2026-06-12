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

## Internal Specs

Internal standards live in `/specs/`:

| Document | Purpose |
|----------|---------|
| `specs/cli-reference.md` | Complete CLI command reference |
| `specs/cli-output.md` | CLI output conventions |
| `specs/code-style.md` | Code style and patterns |
| `specs/patterns.md` | Key patterns (profiles, env chain, tools) |
| `specs/docker.md` | Docker images and naming |
| `specs/ci-cd.md` | CI/CD workflows |
| `specs/tests.md` | Test coverage |

## Commands

```bash
pip install -e ".[dev]"          # editable install with dev deps
python -m pytest tests/ -v       # run tests
ruff check src/ tests/           # lint
mypy src/                        # type-check
python -m codefreedom --help     # CLI (no install needed)
```

## Architecture

```
src/codefreedom/
├── __init__.py      # __version__ from importlib.metadata
├── __main__.py      # python -m codefreedom entry point
├── config.py        # CODEFREEDOM_HOME resolution
├── env_loader.py    # .env chain, eprint()
├── interpolate.py   # ${VAR} interpolation
├── profiles.py      # Profile loading, inheritance
├── tool_registry.py # Reference-counted tool lifecycle
├── launcher.py      # Docker sandbox and native execution
├── admin.py         # Backup/restore engine
├── cli/
│   ├── main.py            # Top-level parser, dispatch
│   ├── agent.py           # Agent launcher with registry
│   ├── config.py          # Unified config dispatcher
│   ├── common.py          # Shared CLI utilities
│   ├── claude.py          # Claude Code agent
│   ├── mimo.py            # MiMoCode agent
│   ├── proxy.py           # Proxy lifecycle
│   ├── tools.py           # Unified tool management
│   ├── docker_utils.py    # Shared Docker helpers
│   └── ...                # Other subcommands
└── schemas/         # Pydantic validation models
```

Entry points: `codefreedom` / `cf` → `src/codefreedom/cli/main.py:main`

## Gotchas

### `eprint` and `_VAR_REF_RE` — single source of truth

`eprint()` is defined once in `env_loader.py`. `_VAR_REF_RE` is defined once in `interpolate.py`. Do not duplicate these in other modules.

### `--dangerously-skip-permissions`

Sandbox mode **always** passes this to Claude CLI inside the container. Local mode only passes it if the user explicitly requests it.

### Unicode breaks Windows CI

**Always use plain ASCII in user-facing strings.** Windows cp1252 cannot encode Unicode box-drawing characters.

### Tool profiles use YAML — not JSON

Tool profiles use `.yaml` files. Legacy `.json` profiles for chrome/web are still supported.

### Proxy is Docker-only — no native mode

The proxy always runs via `docker compose`. No native Python path. Do not reintroduce native-mode logic.

### CustomLogger callbacks: reference `instance`, not the class

Always reference a module-level singleton instance from `config.yaml`, e.g. `plugins.reasoning_efforts_mapping.instance`.

### Patches are baked into the LiteLLM image

Patches in `docker/litellm/patches/` are applied during image build. If you change LiteLLM and a patch can no longer find its target, the build fails loudly.
