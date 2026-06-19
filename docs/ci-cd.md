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
| `release.yml` | workflow_dispatch | Atomic bump + changelog + commit + tag + push |
| `pipy.yaml` | Tag push `v*` | Build + publish to PyPI + GitHub Release |
| `docker-*.yml` | workflow_dispatch | Build, sign, publish Docker images (manual trigger only) |
| `trivy.yml` | Push to main, PRs, weekly | Security scanning |
| `scorecard.yml` | Push to main, weekly | OpenSSF Scorecard |
| `publish-docs.yml` | Push to main (pages changes) | MkDocs to GitHub Pages |

## CI Stages (all in ci.yml)

1. **Lint** — `ruff check src/ tests/`
2. **Type-check** — `mypy src/ --ignore-missing-imports`
3. **Unit tests** — `pytest tests/ -v --tb=short` (Python 3.10/3.11/3.12)
4. **Integration tests** — build wheel, install, smoke test (Ubuntu/Windows/macOS)
5. **Commit lint** — conventional commit validation (PRs only)

## Release Process

Releases are triggered via GitHub Actions `workflow_dispatch` — no local scripts needed.

1. Go to **Actions → Release → Run workflow**
2. Enter version (e.g., `0.2.1`), select type (dev/rc/final)
3. Workflow atomically: bumps version, generates changelog, commits, tags, pushes
4. Tag push triggers `pipy.yaml` for PyPI publish + GitHub Release

See `docs/releasing.md` for full branch strategy and release lifecycle.

## Documentation

```bash
mkdocs serve -a localhost:8080  # local docs preview
```
