# Changelog

All notable changes to this project will be documented in this file.

## [0.1.9]

### Documentation & Discoverability

- Added WebSearch interception documentation (`docs/proxy/websearch-interception.md`)
- Added MiMoCode feature page (`docs/features/mimo-code.md`)
- Clarified recipe sourcing (bundled vs external) in `docs/recipes/index.md` and `recipes/README.md`
- Added troubleshooting guide (`docs/guides/troubleshooting.md`)
- Added FAQ page (`docs/guides/faq.md`)
- Added recipes guide (`docs/guides/recipes-guide.md`)
- Updated navigation with Guides section in `mkdocs.yml`

### Reliability & Test Coverage

- Added launcher tests (`tests/test_launcher.py` — 18 tests)
- Added sandbox launcher tests (`tests/test_sandbox_launcher.py` — 11 tests)
- Added agent dispatch tests (`tests/test_agent_dispatch.py` — 10 tests)
- Added Claude entrypoint tests (`tests/test_claude.py` — 7 tests)
- Added OpenCode entrypoint tests (`tests/test_opencode.py` — 8 tests)
- Added pytest-cov coverage reporting

### Architecture

- Defined canonical config resolution seam (`resolve_agent_config` in `core/config.py`)
- Consolidated tool lifecycle ownership in `tools/registry.py`
- Thinned CLI tool layer (`cli/run/tools.py` delegates to registry)
- Clarified launcher module ownership (launcher.py = agent orchestration, sandbox/launcher.py = container lifecycle)
- Added explicit agent registry helpers (`get_agent_names`, `get_agent_aliases`)
- Added shared CLI validation (`validate_agent_args`)

### Diagnostics

- Expanded `cf doctor` with agent binary checks (Claude, MiMoCode, OpenCode)

### Housekeeping

- Updated `ARCHITECTURE.md` with full module inventory (mimo, opencode, agent, tools, doctor, etc.)
- Updated dependency graph and request flows
- Bumped version to 0.1.9

## [Unreleased]

### Breaking Changes

- **Proxy is Docker-only — native mode removed.** `codefreedom proxy start` now always runs via `docker compose` against `~/.codefreedom/proxy/docker-compose.yaml`. The `--docker` flag has been removed (it was the default; the only other path was native Python, which is gone). The `litellm` extra (`codefreedom[litellm]`) and the `prometheus-client` dependency have been removed from `pyproject.toml` — the proxy image bundles everything it needs. Users upgrading should:
  1. Re-run `codefreedom proxy init` (it will refuse if you already have a config — merge the new `docker-compose.yaml` from the bundled example).
  2. Use `codefreedom proxy start` (no flag).
  3. `codefreedom proxy restart` no longer needs `--docker`.
  4. `pip uninstall codefreedom[litellm]` if you previously installed the extra.
     See `docs/proxy/docker.md` for the architecture.
- **Self-hosted LiteLLM image (`codefreedom:litellm-latest`).** The proxy compose stack no longer pulls `ghcr.io/berriai/litellm`. We now build and publish our own LiteLLM image from `docker/litellm/Dockerfile.LiteLLM`. The image bakes in the WebSearch count display patch at build time — no entrypoint wrapper, no volume mount, no runtime mutation. Tags follow the pattern `litellm-v{MAJOR.MINOR.PATCH}` and `litellm-latest`. Override `LITELLM_IMAGE` in `.env.proxy` to pin a specific version or use a locally-built image. Published via the new `docker-litellm.yml` GitHub Actions workflow.
- **`patch_websearch_count.{py,sh}` removed from bundled examples.** The patch now ships inside the `codefreedom:litellm-latest` image — `codefreedom proxy init` no longer copies these files into `~/.codefreedom/proxy/`. Existing files in `~/.codefreedom/proxy/` are harmless (the new compose file doesn't reference them) but can be deleted.
- **Chrome v0.3.0 — headless refactor.** The Chrome container was rewritten from "Xvfb + stealth + SYS_ADMIN" to plain headless Chrome. This removes `--ipc=host`, `--cap-add=SYS_ADMIN`, Xvfb, PulseAudio, and font packages. The image version bumped from `v0.1.0` to `v0.3.0`. Existing Chrome containers will continue running until restarted, but new `start` commands will use the headless image. For stealth / anti-bot browsing, use the `web` tool (Camoufox) instead.
- **`codefreedom claude vscode` removed.** The old path has been replaced with the dedicated `codefreedom vscode` subcommand. Migrate:
  - `codefreedom claude vscode` → `codefreedom vscode claude config`
  - `codefreedom proxy vscode generate` → `codefreedom vscode proxy config --host HOST`
- **Web Dockerfile user rename: `browser` → `codefreedom`.** The Camoufox container user was renamed from `browser` to `codefreedom` for consistency. Existing containers with data owned by the old `browser` user should be restarted fresh or have their data ownership updated (`chown -R codefreedom:codefreedom`).

### Added

- **Transparent WebSearch replacement via the proxy.** New
  `web-bridge` sidecar (sibling service in the proxy `docker-compose.yaml`)
  translates SearXNG-shaped HTTP requests into JSON-RPC calls against the
  existing Camoufox MCP `web_search` tool. Combined with LiteLLM's
  `websearch_interception` callback, Claude Code's native `WebSearch` is
  silently replaced with a call to the local Camoufox browser — for any
  model behind the proxy, with no client-side configuration. See
  [Web Search Interception](docs/proxy/websearch-interception.md).
  The legacy MCP + `CLAUDE.md` approach in the FAQ is preserved as a
  fallback for `--native-models` users.
- `codefreedom vscode proxy config --host HOST` — generates a
  `chatLanguageModels.json` entry for VS Code from the running LiteLLM proxy.
  Reads `/v1/model/info` using `LITELLM_MASTER_KEY` (from env or
  `~/.codefreedom/.env.proxy.secrets`), probes `/health/liveliness` to verify
  the proxy is up, and emits a JSON object with `toolCalling` / `vision` /
  token-limit fields derived from the proxy response.
- `codefreedom vscode claude config [--profile NAME]` — generates a
  `claudeCode.*` settings.json fragment for the Anthropic Claude Code VS Code
  extension. Replaces `codefreedom claude vscode`.

### Changed

- **VS Code config moved to a dedicated subcommand.** `codefreedom claude
vscode` and `codefreedom proxy vscode generate` have been moved to a
  top-level `codefreedom vscode {claude,proxy} config` command. The old paths
  are no longer recognised. Use `codefreedom vscode claude config` and
  `codefreedom vscode proxy config --host HOST` respectively. All VS Code
  integration logic has been consolidated into `src/codefreedom/cli/vscode.py`.

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

- `codefreedom proxy` subcommand with `start`, `stop`, `status`, `validate`, `--docker` actions
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
