# Changelog

All notable changes to CodeFreedom will be documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/) and
[Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased]

### Added

- Branching strategy documentation (`docs/releasing.md`)
- Changelog generation via git-cliff
- `--bump-rc` and `--create-release-branch` flags in `release.sh`
- Git commit hash in `cf --version` for dev builds
- CI triggers on PRs to `prerelease/*` and `release/*` branches

### Changed

- Release script accepts `release/v*` branches for RC tags (was hardcoded to `prerelease`)
- Release candidate number limit removed (was capped at 10)

## [0.2.0] - 2026-06-14

### Added

- Recipe system with cross-recipe sync
- Web bridge (SearXNG integration)
- Chrome headless MCP redesign
- VS Code subcommand
- `cf update` CLI command
- `codefreedom update` CLI command

### Fixed

- LiteLLM Docker build issues
- Chrome tool directory structure
- Proxy config validation

## [0.1.0] - 2026-03-XX

### Added

- Initial release
- LLM proxy routing via LiteLLM
- Docker sandboxing with GPU support (CUDA, ROCm)
- Profile management with env inheritance
- Browser tools (Chrome CDP, Camoufox)
- GitHub MCP integration
- CLI with setup/run/manage lifecycle groups
