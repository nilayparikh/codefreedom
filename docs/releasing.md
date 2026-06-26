# Release Process

## Overview

CodeFreedom uses a Gitflow-inspired branching strategy with GitHub Actions for all releases.
No local release scripts -- everything runs in CI via `workflow_dispatch`.

`version.yaml` is the single source of truth for versioning. `pyproject.toml` is derived at release time and should never be edited on branches.

## Branch Structure

```text
main                              <- stable releases (final tags only)
  ^ merge release when approved
release/v0.2.1                    <- RC testing (rc tags -> PyPI)
  ^ created from prerelease
prerelease/v0.2.1                 <- feature consolidation (dev tags -> PyPI)
  ^ PRs from features
feature/add-docker-gpu            <- individual work
```

## Branch Naming

| Type | Pattern | Example | Lifecycle |
|---|---|---|---|
| Feature | `feature/{short-name}` | `feature/docker-gpu` | Delete after merge to prerelease |
| Pre-release | `prerelease/v{version}` | `prerelease/v0.2.1` | Delete after promotion to release |
| Release | `release/v{version}` | `release/v0.2.1` | Delete after merge to main |

## Tag Naming (PEP 440)

| Tag | PyPI action | Example |
|---|---|---|
| `vX.Y.Z.devN` | Publishes as pre-release (`pip install --pre`) | `v0.2.1.dev1` |
| `vX.Y.ZrcN` | Publishes as pre-release (`pip install --pre`) | `v0.2.1rc1` |
| `vX.Y.Z` | Publishes as stable release | `v0.2.1` |

## Version in pyproject.toml

| Branch | Version format | Example |
|---|---|---|
| `feature/*` | `X.Y.Z` | `0.2.1` |
| `prerelease/*` | `X.Y.Z.devN` | `0.2.1.dev1` |
| `release/*` | `X.Y.ZrcN` | `0.2.1rc1` |
| `main` | `X.Y.Z` | `0.2.1` |

For local testing, install directly:

```bash
pip install -e ".[all]"
```

## Release Workflow

All releases are triggered via GitHub Actions `workflow_dispatch`.
No local scripts -- everything runs in CI atomically.

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
# Optionally trigger dev release:
#   Actions -> Publish Dev -> Run workflow
```

### Phase 3: Release Candidate

```bash
git checkout prerelease/v0.2.1
git checkout -b release/v0.2.1
git push -u origin release/v0.2.1

# Trigger RC release from GitHub:
#   Actions -> Publish RC -> Run workflow

# Found a bug? Fix on release branch, then trigger again.
```

### Phase 4: Final Release

```bash
# Merge release branch to main:
git checkout main
git merge release/v0.2.1
git push origin main

# Trigger final release from GitHub:
#   Actions -> Publish Final -> Run workflow

# Cleanup
git branch -d release/v0.2.1
git push origin --delete release/v0.2.1
git branch -d prerelease/v0.2.1
git push origin --delete prerelease/v0.2.1
```

## Workflows

### CI (`ci.yml`)

Single workflow for all branches and PRs.

| Trigger | What runs |
|---|---|
| Push to ANY branch | Lint, type-check, unit tests (3.10/3.11/3.12), integration tests (Ubuntu/Windows/macOS) |
| PR to main/prerelease/v*/release/v* | Same as above + conventional commit lint |

**Stages:**

1. **Lint** -- `ruff check src/ tests/`
2. **Type-check** -- `mypy src/ --ignore-missing-imports`
3. **Unit tests** -- `pytest tests/ -v --tb=short` (Python 3.10/3.11/3.12)
4. **Integration tests** -- build wheel, install, smoke test (Ubuntu/Windows/macOS)
5. **Commit lint** -- conventional commit validation (PRs only)

### Publish Dev (`publish-dev.yml`)

Manual dispatch only (`workflow_dispatch`). Must be on a `dev/v*` branch.

Reads `version.yaml` to build the version string `{version}rc{rc}.dev{dev}`.

### Publish RC (`publish-rc.yml`)

Manual dispatch only (`workflow_dispatch`). Must be on an `rc/v*` branch.

Reads `version.yaml` to build the version string `{version}rc{rc}`.

### PyPI Publish (`pipy.yaml`)

Manual dispatch only (`workflow_dispatch`). 100% user-controlled -- no auto-trigger on tag push or any other event.

| Step | Description |
|---|---|
| Test | Run full test suite on 3 OS x 3 Python versions |
| Build | Create sdist + wheel |
| Publish | Upload to PyPI via OIDC trusted publishing |
| GitHub Release | Create release (marked as pre-release for dev/rc) |

### Docker Workflows

All Docker workflows are manual trigger only (`workflow_dispatch`).

| Workflow | Image | Inputs |
|---|---|---|
| `docker-chrome.yml` | Chrome browser | `tag` (required), `latest` (default: true) |
| `docker-litellm.yml` | LiteLLM proxy | `tag` (required), `latest` (default: true), `litellm_base_tag` (optional) |
| `docker-web.yml` | Camoufox MCP | `tag` (required), `latest` (default: true) |
| `docker-web-bridge.yml` | Web Bridge | `tag` (required), `latest` (default: true) |
| `docker-github.yml` | GitHub MCP | `tag` (required), `latest` (default: true) |
| `docker-litellm-base.yml` | LiteLLM base | `litellm_tag` (required), `pg_base_tag` (required) |
| `docker-litellm-pg-base.yml` | PostgreSQL base | `pg_version` (required), `pg_tag` (required) |

### Other Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `trivy.yml` | Push to main, PRs, weekly | Security scanning |
| `publish-docs.yml` | Push to main (docs changes) | MkDocs to GitHub Pages |

## What Triggers PyPI Release

Only manual dispatch triggers the publish workflows.
No auto-trigger on tag push, merge, or branch push.

| Action | PyPI Release? |
|---|---|
| Push to feature/* | No |
| Push to prerelease/v* | No |
| Push to release/v* | No |
| Push to main | No |
| PR to any branch | No |
| Tag push (v*) | No |
| Trigger publish-dev.yml | Yes (dev pre-release) |
| Trigger publish-rc.yml | Yes (RC pre-release) |
| Trigger pipy.yaml | Yes (final or pre-release) |

## Branch Protection

All protected branches use a single rule with pattern:

```text
main
prerelease/v*
release/v*
```

**Required settings:**

- Require a pull request before merging
- Require status checks to pass before merging:
    - `unit-tests (3.10)`
    - `unit-tests (3.11)`
    - `unit-tests (3.12)`
    - `integration (ubuntu-24.04 / py3.12)`
    - `integration (windows-2022 / py3.12)`
    - `integration (macos-14 / py3.12)`
    - `Validate commit messages`
- Require branches to be up to date before merging

## Commit Message Format

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

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

PRs to `prerelease/v*` and `release/v*` branches are validated automatically.

## Local Development

For local testing, install in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
```

The version in `pyproject.toml` is bumped only at release time via CI workflows. `version.yaml` is the source of truth.
