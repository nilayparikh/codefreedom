---
title: Contribute
description: How to contribute to CodeFreedom.
---

# Contribute

Contributions are welcome. Here's how to get started.

## Development Setup

```bash
git clone https://github.com/nilayparikh/codefreedom.git
cd codefreedom
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run Tests

```bash
python -m pytest tests/ -v --tb=short
```

## Lint and Type-Check

```bash
ruff check src/ tests/
mypy src/
```

## Submit a Pull Request

1. Fork the repository
2. Create a branch from `main`
3. Make your changes with descriptive commits
4. Run the tests
5. Open a Pull Request

## Coding Standards

- **Python:** PEP 8, type hints required
- **YAML:** 2-space indentation
- **Commits:** Imperative mood ("Add feature", not "Added feature")

## Principles

- **No hacking.** CodeFreedom integrates through publicly documented interfaces only — environment variables, CLI flags, config files, API endpoints.
- **Just configuration.** Profiles are environment variables. Proxy routing is standard LiteLLM config.
- **Opt-in providers.** Set an API key to enable a provider. Leave it empty to disable.

## Code of Conduct

This project follows the [Contributor Covenant](https://github.com/nilayparikh/codefreedom/blob/main/CODE_OF_CONDUCT.md). Be respectful and inclusive.

## Questions?

Open a [GitHub Issue](https://github.com/nilayparikh/codefreedom/issues) or Discussion.
