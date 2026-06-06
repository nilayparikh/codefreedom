# License & Contributions

## Principles

CodeFreedom is a **unified interface for all code agents** — it integrates through
**publicly supported features only**.

- **No hacking.** CodeFreedom does not reverse-engineer, patch, modify, or tamper
  with any code agent (Claude Code, VS Code, Cursor, Codex, or others). Every
  integration uses only documented, public interfaces — environment variables,
  CLI flags, config files, and API endpoints.
- **Just configuration.** Profiles are environment variables. Proxy routing is
  standard LiteLLM config. No binary patching, no internal API abuse.
- **All config in one place.** `~/.codefreedom` is the single source of truth for
  profiles, proxy settings, and sandbox configuration.
- **Trademarks belong to their owners.** See [`NOTICE`](https://github.com/nilayparikh/codefreedom/blob/main/NOTICE)
  for a full list of trademark attributions.

---

## License

CodeFreedom is licensed under the **Apache License, Version 2.0**.

```
Copyright 2025-2026 Nilay Parikh

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

See the full [LICENSE](https://github.com/nilayparikh/codefreedom/blob/main/LICENSE) file in the repository.

## Contributing

Contributions are welcome! Here's how to get started.

### Development Setup

```bash
git clone https://github.com/nilayparikh/codefreedom.git
cd codefreedom
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run Tests

```bash
python -m pytest tests/ -v --tb=short
```

### Submit a Pull Request

1. Fork the repository
2. Create a branch from `main`
3. Make your changes with descriptive commits
4. Run the tests
5. Open a Pull Request

### Coding Standards

- **Python:** PEP 8, type hints required
- **YAML:** 2-space indentation
- **Commits:** Imperative mood ("Add feature", not "Added feature")

## Code of Conduct

This project follows the [Contributor Covenant](https://github.com/nilayparikh/codefreedom/blob/main/CODE_OF_CONDUCT.md). Be respectful and inclusive.

## Questions?

Open a [GitHub Issue](https://github.com/nilayparikh/codefreedom/issues) or Discussion.
