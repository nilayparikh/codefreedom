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

| Workflow | Purpose |
|----------|---------|
| `integration-test.yml` | Tests on Python 3.10/11/12 across Ubuntu, Windows, macOS |
| `docker-*.yml` | Build, sign, publish Docker images |
| `pipy.yaml` | Publish to PyPI on `v*` tags |
| `trivy.yml` | Security scanning |

## Release Process

```bash
./scripts/release.sh  # bumps version, tags, publishes
```

## Documentation

```bash
mkdocs serve -a localhost:8080  # local docs preview
```
