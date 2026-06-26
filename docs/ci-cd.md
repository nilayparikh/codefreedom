# CI/CD Workflows

GitHub Actions workflows for testing, building, and publishing.

## Quick Reference

```bash
# Run tests locally
python -m pytest tests/ -v

# Lint
ruff check src/ tests/

# Type-check
mypy src/
```

## Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci.yml` | Push to ANY branch + PRs | Lint, type-check, unit tests, integration tests, commit lint (PRs only) |
| `publish-dev.yml` | workflow_dispatch | Build + publish dev version to PyPI (`dev/v*` only) |
| `publish-rc.yml` | workflow_dispatch | Build + publish RC version to PyPI (`rc/v*` only) |
| `pipy.yaml` | workflow_dispatch | Build + publish final version to PyPI + GitHub Release (manual only) |
| `docker-chrome.yml` | workflow_dispatch | Build, sign, publish Chrome Docker image |
| `docker-litellm.yml` | workflow_dispatch | Build, sign, publish LiteLLM Docker image |
| `docker-web.yml` | workflow_dispatch | Build, sign, publish Camoufox MCP Docker image |
| `docker-web-bridge.yml` | workflow_dispatch | Build, sign, publish Web Bridge Docker image |
| `docker-github.yml` | workflow_dispatch | Build, sign, publish GitHub MCP Docker image |
| `docker-litellm-base.yml` | workflow_dispatch | Build, sign, publish LiteLLM base Docker image |
| `docker-litellm-pg-base.yml` | workflow_dispatch | Build, sign, publish PostgreSQL base Docker image |
| `trivy.yml` | Push to main, PRs, weekly | Security scanning |
| `publish-docs.yml` | Push to main (pages changes) | MkDocs to GitHub Pages |

## CI Stages (all in ci.yml)

1. **Lint** — `ruff check src/ tests/`
2. **Type-check** — `mypy src/ --ignore-missing-imports`
3. **Unit tests** — `pytest tests/ -v --tb=short` (Python 3.10/3.11/3.12)
4. **Integration tests** — build wheel, install, smoke test (Ubuntu/Windows/macOS)
5. **Commit lint** — conventional commit validation (PRs only)

## Release Process

Releases are triggered via GitHub Actions `workflow_dispatch` -- no local scripts needed.

1. Go to **Actions -> Release -> Run workflow**
2. Enter version (e.g., `0.2.1`), select type (dev/rc/final)
3. Workflow atomically: bumps version, generates changelog, commits, tags, pushes
4. Manually trigger `pipy.yaml` to publish to PyPI + create GitHub Release

See `docs/releasing.md` for full branch strategy and release lifecycle.

## Documentation

```bash
mkdocs serve -a localhost:8080  # local docs preview
```
