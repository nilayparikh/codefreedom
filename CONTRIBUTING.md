# Contributing to CodeFreedom

Thank you for your interest in contributing to **CodeFreedom**! This document outlines the process for contributing to the project.

## Prerequisites

Before you begin, ensure your development environment meets these requirements:

- **Python** 3.10+
- **Docker** ≥ 24.x (with Compose plugin) — for Docker mode and LiteLLM proxy
- **Node.js** + `@anthropic-ai/claude-code` — for native/local Claude Code mode
- Git

## Development Environment Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/nilayparikh/codefreedom.git
   cd codefreedom
   ```

2. **Create a virtual environment and install:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Run the tests:**

   ```bash
   python -m pytest tests/ -v --tb=short
   ```

## Pull Request Process

1. **Fork** the repository.
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes and commit with descriptive messages.
4. **Push** your branch and open a Pull Request against `main`.
5. Use a **descriptive PR title** that summarizes the change.
6. **Link related issues** in the PR description using GitHub keywords (`fixes #123`, `refs #456`).

## Coding Standards

- **Python:** Follow PEP 8. Use type hints for all function signatures.
- **YAML:** Use 2-space indentation consistently.
- **Commit messages:** Write meaningful, imperative commit messages.
- **File naming:** Use kebab-case for configuration and docs; snake_case for Python modules.

## Testing Requirements

Before submitting a Pull Request:

1. **Run unit tests:** `python -m pytest tests/ -v --tb=short`
2. **Smoke test the CLI:** `codefreedom --help` and `cf --help`
3. **Test `--init`:** `codefreedom --init --force` and verify `~/.codefreedom/` structure
4. **Test profile listing:** `codefreedom run agent claude-code --list-profiles`

## Documentation Updates

**Every feature change must include documentation updates in the same Pull Request.** At minimum:

- Update relevant `.md` files in `docs/` if user-facing behavior changes
- Update the root `README.md` for significant new features
- Update `mkdocs.yml` navigation if new pages are added

## Code of Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before participating.

## Questions?

Open a GitHub Discussion or Issue in the repository.
