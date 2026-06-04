# Release v0.1.0

> Published: 2026-06-04 | Branch: `alpha-release`

## Summary

This release introduces three major new capabilities: the `admin` subcommand for config backup/restore, the `tools chrome` and `tools web` commands for browser automation containers, and significant proxy enhancements. The Camoufox component has been renamed to "Web" for clarity.

---

## New Features

### `codefreedom admin` Subcommand

A new top-level subcommand for managing CodeFreedom configuration backups:

- **`backup`** — Create a backup of `~/.codefreedom` (excludes secrets)
- **`restore PATH`** — Restore from a backup with interactive diff preview
- **`list-backups`** — List all available backups
- **`inspect PATH`** — Show manifest contents of a backup archive
- **`prune`** — Delete old backups (`--keep N` or `--older-than` duration)

Full implementation in `src/codefreedom/admin.py` and `src/codefreedom/cli/admin.py` with comprehensive test coverage in `tests/test_admin.py`.

### `codefreedom tools chrome` Command

Manage a Chromium browser container for headless/headed browser automation:

- **`init`** — Initialize Chrome tool profile (requires user acceptance)
- **`start`** — Launch Xvfb + Chromium container with CDP on port 9222
- **`stop`** — Stop the Chrome container
- **`restart`** — Restart without image pull (preserves state)
- **`status`** — Show container status
- **`url`** — Print CDP debug URL for agent connection

### `codefreedom tools web` Command (formerly Camoufox)

Manage a Camoufox MCP server container for stealth web search and scraping:

- **`init`** — Initialize Web tool profile (requires user acceptance)
- **`start`** — Launch Camoufox container (MCP server on port 8420)
- **`stop`** — Stop the container
- **`restart`** — Restart without image pull (preserves state)
- **`status`** — Show container status

### Proxy Enhancements

- **`proxy restart --docker`** — Restart via Docker Compose (preserves state, no image pull)
- **`proxy validate`** — Validate proxy configuration
- **`--host HOST`** — Set custom bind host (default: `0.0.0.0`)
- **`--port PORT`** — Set custom proxy port (default: `4000`)
- Improved Docker Compose discovery and config validation

### New Optional Dependency

- **`encrypt`** — `cryptography>=42.0` for encrypted config support

---

## Refactoring

### Camoufox -> Web Rename

Complete rename of the "Camoufox" component to "Web" across the entire codebase:

- Docker files: `docker/web/` directory, `Dockerfile.Web`
- CLI: `src/codefreedom/cli/web.py`
- Docs: `docs/tools/web.md`
- Examples: `src/codefreedom/examples/tools/web/`
- Docker images: `codefreedom:web` tag

### Documentation Restructure

- **`docs/proxy.md`** split into `docs/proxy/` directory:
  - `index.md` — Proxy overview
  - `config.md` — Configuration guide
  - `database.md` — Optional PostgreSQL setup
  - `docker.md` — Docker Compose deployment
  - `providers/` — Provider-specific guides (Anthropic, Azure, DeepSeek, NVIDIA, OpenAI, OpenRouter, OpenCode Zen, Local)
- **New docs:**
  - `docs/admin.md` — Admin subcommand reference
  - `docs/claude-code/profiles.md` — Profile configuration guide
  - `docs/claude-code/sandbox-isolation.md` — Sandbox isolation details
- Updated `mkdocs.yml` site navigation to reflect new structure

---

## Improvements

- **Tool registry** — Reference-counted tool lifecycle via `~/.codefreedom/proc/`
- **Tool init** — Shared acceptance prompt and notices in `tool_init_utils.py`
- **Docker utilities** — Shared start/stop/status helpers in `docker_utils.py`
- **Init utilities** — Bundled examples resolution, all-or-nothing file copy
- **Config** — Added `CODEFREEDOM_HOME` resolution improvements
- **Env loader** — Minor parsing improvements
- **Launcher** — Updated Docker sandbox and native local execution
- **Proxy config** — Added `openrouter.yaml` provider example
- **Test coverage** — New `test_admin.py`, `test_chrome.py`, `test_web.py`

---

## Files Changed

| Area | Files |
|---|---|
| **New source** | `admin.py`, `cli/admin.py`, `cli/chrome.py` (expanded), `cli/web.py` |
| **Modified source** | `cli/claude.py`, `cli/main.py`, `cli/proxy.py`, `cli/init_utils.py`, `cli/tool_init_utils.py`, `config.py`, `env_loader.py`, `launcher.py`, `tool_registry.py` |
| **New tests** | `test_admin.py`, `test_chrome.py`, `test_web.py` |
| **Modified tests** | `conftest.py`, `test_proxy.py` |
| **New docs** | `admin.md`, `profiles.md`, `sandbox-isolation.md`, `docs/proxy/` (7 files) |
| **Modified docs** | `architecture.md`, `claude-code.md`, `local.md`, `sandbox.md`, `environment.md`, `index.md`, `tools/index.md`, `tools/web.md`, `troubleshooting.md`, `vscode.md` |
| **Config** | `pyproject.toml`, `mkdocs.yml`, Docker files, example configs |

---

## Upgrade Notes

- **Breaking:** `camoufox` optional dependency renamed to `web` in usage (install still uses package name). Users should run `codefreedom tools web init` instead of any prior Camoufox-specific commands.
- **New:** Run `codefreedom admin backup` after upgrading to create your first config backup.
- **New:** Browser tool users should run `codefreedom tools chrome init` and/or `codefreedom tools web init` before starting containers.

---

## Checksums

| File | SHA-256 |
|---|---|
| *(to be filled after PyPI publish)* | |

---

## Installation

```bash
pip install --upgrade codefreedom
# or
pip install -e ".[all]"
```

---

## Pre-release Checklist

- [x] Version bumped in `pyproject.toml`
- [x] Tag `v0.1.0` created (annotated)
- [x] Release notes drafted
- [ ] Tests pass (`python -m pytest tests/ -v`)
- [ ] Lint passes (`ruff check src/ tests/`)
- [ ] Type check passes (`mypy src/`)
- [ ] Push to remote (`git push origin alpha-release && git push origin v0.1.0`)
- [ ] Create GitHub release from tag
- [ ] Merge `alpha-release` into `main`
- [ ] Publish to PyPI (triggered by `v*` tag via `pipy.yaml` workflow)
