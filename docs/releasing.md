# Release Process

## Overview

CodeFreedom uses a Gitflow-inspired branching strategy with GitHub Actions for all releases.
No local release scripts — everything runs in CI via `workflow_dispatch`.

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
# Optionally trigger dev release:
#   Actions -> Release -> Run workflow
#     version: 0.2.1
#     pre-release: true
#     type: dev
#     dev-number: 1
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
#   type: rc
#   candidate: 1

# Found a bug? Fix on release branch, then trigger again:
#   version: 0.2.1
#   pre-release: true
#   type: rc
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

## Workflows

### CI (`ci.yml`)

Single workflow for all branches and PRs.

| Trigger | What runs |
|---|---|
| Push to ANY branch | Lint, type-check, unit tests (3.10/3.11/3.12), integration tests (Ubuntu/Windows/macOS) |
| PR to main/prerelease/v*/release/v* | Same as above + conventional commit lint |

**Stages:**

1. **Lint** — `ruff check src/ tests/`
2. **Type-check** — `mypy src/ --ignore-missing-imports`
3. **Unit tests** — `pytest tests/ -v --tb=short` (Python 3.10/3.11/3.12)
4. **Integration tests** — build wheel, install, smoke test (Ubuntu/Windows/macOS)
5. **Commit lint** — conventional commit validation (PRs only)

### Release (`release.yml`)

Atomic release via `workflow_dispatch`.

| Input | Required | Description |
|---|---|---|
| `version` | Yes | Base version (e.g., `0.2.1`) |
| `pre-release` | No | Mark as pre-release (default: false) |
| `type` | No | Pre-release type: `dev` or `rc` (default: `rc`) |
| `candidate` | No | RC number (required if type=rc) |
| `dev-number` | No | Dev number (required if type=dev) |

**What it does:**

1. Validates version format, branch, clean working tree, no duplicate tags
2. Builds full version string: `X.Y.Z.devN`, `X.Y.ZrcN`, or `X.Y.Z`
3. Bumps version in `pyproject.toml`
4. Generates changelog with `git-cliff`
5. Commits: `release: bump to X.Y.Z.devN` or `release: bump to X.Y.ZrcN`
6. Tags: creates annotated tag
7. Pushes commit + tag to origin

**Branch requirements:**

| Release type | Must be on |
|---|---|
| Dev (`type=dev`) | `prerelease/v*` branch |
| RC (`type=rc`) | `release/v*` branch |
| Final (`pre-release=false`) | `main` branch |

### PyPI Publish (`pipy.yaml`)

Triggered by tag push `v*`. Builds and publishes to PyPI.

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
| `docker-cuda.yml` | CUDA GPU | `tag` (required), `latest` (default: true) |
| `docker-rocm.yml` | ROCm GPU | `tag` (required), `latest` (default: true) |
| `docker-ubuntu.yml` | CPU-only | `tag` (required), `latest` (default: true) |
| `docker-litellm.yml` | LiteLLM proxy | `tag` (required), `latest` (default: true), `litellm_base_tag` (optional) |
| `docker-mimo-code.yml` | MiMo Code | `tag` (required), `latest` (default: true) |
| `docker-open-code.yml` | Open Code | `tag` (required), `latest` (default: true) |
| `docker-web.yml` | Camoufox MCP | `tag` (required), `latest` (default: true) |
| `docker-web-bridge.yml` | Web Bridge | `tag` (required), `latest` (default: true) |
| `docker-github.yml` | GitHub MCP | `tag` (required), `latest` (default: true) |
| `docker-litellm-base.yml` | LiteLLM base | `litellm_tag` (required), `pg_base_tag` (required) |
| `docker-litellm-pg-base.yml` | PostgreSQL base | `pg_version` (required), `pg_tag` (required) |

### Other Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `trivy.yml` | Push to main, PRs, weekly | Security scanning |
| `scorecard.yml` | Push to main, weekly | OpenSSF Scorecard |
| `publish-docs.yml` | Push to main (docs changes) | MkDocs to GitHub Pages |

## What Triggers PyPI Release

Only tag pushes matching `v*` trigger the `pipy.yaml` workflow.
Merging PRs or pushing branches never triggers a release.

| Action | PyPI Release? |
|---|---|
| Push to feature/* | No |
| Push to prerelease/v* | No |
| Push to release/v* | No |
| Push to main | No |
| PR to any branch | No |
| Trigger release.yml | Tag push -> PyPI publish |

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

The version in `pyproject.toml` is bumped only at release time via the `release.yml` workflow.
