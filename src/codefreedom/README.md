# `codefreedom` Package

Core Python package for [CodeFreedom](../../README.md) — a unified CLI wrapper for code agents with simple LLM routing, sandboxing, and profile management.

## Module Overview

| Module             | Purpose                                                                                              |
| ------------------ | ---------------------------------------------------------------------------------------------------- |
| `__init__.py`      | Package root; derives `__version__` from `importlib.metadata` (source of truth: `pyproject.toml`).   |
| `__main__.py`      | Entry point for `python -m codefreedom`; dispatches to `cli.main.main()`.                            |
| `config.py`        | Centralized path resolution for `~/.codefreedom/` (overridable via `CODEFREEDOM_HOME`).              |
| `profiles.py`      | Profile JSON loading, `${VAR}` interpolation, and inheritance between profiles.                      |
| `env_loader.py`    | Multi-tier `.env` chain: component-specific → shared → workspace → system env.                       |
| `launcher.py`      | Docker sandbox lifecycle — ephemeral containers with GPU passthrough (CUDA/ROCm).                    |
| `tool_registry.py` | Reference-counted tool lifecycle via `~/.codefreedom/proc/` (first session starts, last stops).      |
| `admin.py`         | Backup/restore engine — archives config with secret redaction and optional AES-256 encryption.       |
| `cli/`             | CLI subcommands (`claude`, `proxy`, `tools`, `admin`, `vscode`). See `CLAUDE.md` for full reference. |
| `recipes/`         | Configuration recipes from github.com/nilayparikh/codefreedom-recipes.                               |

## Key Patterns

### Profile Inheritance

Custom profiles inherit from `default`. A profile's `env` merges on top of its parent's. Mode-specific overrides (`sandbox.env`, `local.env`) follow the same pattern.

### Environment Variable Chain

Each subcommand loads a 7-layer env chain (component-specific → shared → workspace → system). Empty-string vars are valid overrides — they do NOT fall through to defaults.

### Tool Lifecycle

Tools declared in a profile (`"tools": ["chrome", "web"]`) use reference counting. The first session to need a tool starts its container; the last session to exit stops it. Stale sessions from crashes are cleaned on startup.

### Sandbox Containers

Ephemeral containers (`codefreedom-XXXX`) run `sleep infinity`; the code agent is `docker exec`'d into them. Containers are auto-removed on exit via `--rm` and a `finally` fallback.

## Testing

All tests live in `tests/` and use `tmp_path` + `monkeypatch` for path isolation — never touching real `~/.codefreedom/` during tests.

```bash
python -m pytest tests/ -v
```
