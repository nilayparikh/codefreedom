# Changelog

All notable changes to this project will be documented in this file.

## [0.0.3] - 2026-06-02

### Added

- MkDocs Material documentation site with Mermaid diagrams, dark mode, and search
- Mermaid architecture diagrams replacing ASCII art
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `NOTICE` community files
- `CHANGELOG.md` for version history
- GitHub issue templates (bug report, feature request) and PR template
- Dependabot configuration for automated dependency updates
- `CODEOWNERS` file
- Lint workflow (YAML lint + Python syntax check)
- Trivy security scanning workflow
- Documentation dev dependencies (`mkdocs-material`, `mkdocs-mermaid2-plugin`)

### Changed

- Rewrote `publish-docs.yml` to use MkDocs Material instead of Jekyll
- Restructured documentation with proper nav hierarchy and new pages
- Updated `README.md` with Mermaid architecture diagram

### Removed

- Deleted `litellm_cli.py` (dead code — superseded by `proxy.py`)
- Deleted Jekyll `_config.yml` (replaced by `mkdocs.yml`)

## [0.0.2] - 2026-05-XX

### Added

- `codefreedom proxy` subcommand with `--up`, `--down`, `--status`, `--validate`, `--docker` flags
- Cross-platform CI (ubuntu, windows, macos)
- Support for `.env` and `.env.secrets` env loading
- Sandbox mode (`--sandbox`) with ephemeral Docker containers

### Fixed

- Path resolution for proxy configs now uses `~/.codefreedom/`

## [0.0.1] - 2026-05-XX

### Added

- Initial release of CodeFreedom CLI
- `codefreedom claude` / `cf cc` subcommand for launching Claude Code
- Profile-based model routing with `--profile` flag
- `codefreedom --init` for bootstrapping `~/.codefreedom/`
- LiteLLM proxy management
- Native and Docker execution modes for Claude Code
- PyPI package publishing
