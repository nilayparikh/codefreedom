# Release Process

## Branch Structure

```text
main                              <- stable releases (final tags only)
  ^ merge release when approved
release/v0.2.1                    <- RC testing (rc tags -> PyPI)
  ^ created from prerelease
prerelease/v0.2.1                 <- feature consolidation (no tags -> no PyPI)
  ^ PRs from features
feature/add-docker-gpu            <- individual work
```

## Branch Naming

| Type | Pattern | Example |
|---|---|---|
| Feature | `feature/{short-name}` | `feature/docker-gpu` |
| Pre-release | `prerelease/v{version}` | `prerelease/v0.2.1` |
| Release | `release/v{version}` | `release/v0.2.1` |
| Tag (RC) | `v{X.Y.Z}rc{N}` | `v0.2.1rc1` |
| Tag (final) | `v{X.Y.Z}` | `v0.2.1` |

## Version in pyproject.toml

| Phase | Version | Example |
|---|---|---|
| Development | `X.Y.Z` | `0.2.1` |
| Release candidate | `X.Y.ZrcN` | `0.2.1rc1` |
| Final release | `X.Y.Z` | `0.2.1` |

No `.devN` suffixes. For local testing, install directly:

```bash
pip install -e ".[all]"
```

## Release Workflow

All releases are triggered via GitHub Actions `workflow_dispatch`.
No local scripts — everything runs in CI atomically.

### Phase 1: Feature Development

```bash
git checkout main && git pull
git checkout -b feature/docker-gpu
# work, commit (conventional commits), push
# PR -> prerelease/v0.2.1
```

### Phase 2: Consolidation

```bash
git checkout prerelease/v0.2.1
# Merge PRs from feature branches
```

### Phase 3: Release Candidate

```bash
git checkout prerelease/v0.2.1
git checkout -b release/v0.2.1
git push -u origin release/v0.2.1

# Trigger release from GitHub:
# Actions -> Release -> Run workflow
#   version: 0.2.1
#   pre-release: true
#   candidate: 1

# Found a bug? Fix on release branch, then trigger again:
#   version: 0.2.1
#   pre-release: true
#   candidate: 2
```

### Phase 4: Final Release

```bash
# Merge release branch to main:
git checkout main
git merge release/v0.2.1
git push origin main

# Trigger release from GitHub:
# Actions -> Release -> Run workflow
#   version: 0.2.1
#   pre-release: false

# Cleanup
git branch -d release/v0.2.1
git push origin --delete release/v0.2.1
git branch -d prerelease/v0.2.1
git push origin --delete prerelease/v0.2.1
```

## CI Workflows

All CI is consolidated into a single `ci.yml` workflow.

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci.yml` | Push to ANY branch + PRs to main/pre-release/release | Lint, type-check, unit tests, integration tests, commit lint (PRs only) |
| `release.yml` | workflow_dispatch | Atomic bump + changelog + commit + tag + push |
| `pipy.yaml` | Tag push `v*` | Build + publish to PyPI + GitHub Release |
| `docker-*.yml` | workflow_dispatch | Build, sign, publish Docker images |
| `trivy.yml` | Various | Security scanning |
| `scorecard.yml` | Various | OpenSSF Scorecard |
| `publish-docs.yml` | Various | MkDocs deployment |

### CI Stages (all in ci.yml)

1. **Lint** — `ruff check src/ tests/`
2. **Type-check** — `mypy src/ --ignore-missing-imports`
3. **Unit tests** — `pytest tests/ -v --tb=short` (Python 3.10/3.11/3.12)
4. **Integration tests** — build wheel, install, smoke test (Ubuntu/Windows/macOS)
5. **Commit lint** — conventional commit validation (PRs only)

## What Triggers PyPI Release

Only tag pushes matching `v*` trigger the `pipy.yaml` workflow.
Merging PRs never triggers a release.

| Action | PyPI Release? |
|---|---|
| Push to feature/* | No |
| Push to prerelease/v* | No |
| Push to release/v* | No |
| Push to main | No |
| PR to any branch | No |
| Trigger release.yml | Tag push -> PyPI publish |

## Commit Message Format

```text
type(scope): description

# Types:
feat     - new feature
fix      - bug fix
perf     - performance improvement
refactor - code change that neither fixes a bug nor adds a feature
doc      - documentation only
ci       - CI/CD changes
chore    - maintenance tasks
test     - adding or updating tests
style    - formatting, no code change
revert   - reverts a previous commit
```
