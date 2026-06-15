# Test Architecture

## Purpose

Tests verify CodeFreedom's correctness at two levels:

1. **Unit tests** — pure logic with zero I/O. Fast (runs in <2s), deterministic, no side effects.
2. **Integration tests** — exercise filesystem, subprocess, Docker, or network. Slower (~10s), may need mocking.

## Methodology

### What Belongs Where

| Category | Marker | Typical Content | Example |
|----------|--------|-----------------|---------|
| **Unit** | `@pytest.mark.unit` | Pure functions, transforms, parsers, validation logic | `_categorize()`, `_deepdiff_merge()`, `_resolve_model_id()` |
| **Integration** | `@pytest.mark.integration` | I/O, Docker, subprocess, network, full CLI commands | `engine_backup()`, `cmd_vscode_proxy_config()`, `_check_proxy_live()` |

### Decision Rule

Ask: **"Does this test read/write files, call subprocess, or make network requests (even mocked)?"**

- **Yes** → integration
- **No** → unit

If a test uses `tmp_path` for filesystem assertions (not just as a throwaway), it's integration. If `tmp_path` is only used to set `CODEFREEDOM_HOME` for env-var resolution, it's unit.

### Running Tests

```bash
# All tests (default)
pytest tests/ -q

# Unit only (fast, ~2s)
pytest tests/ -m unit -q

# Integration only (slower, ~10s)
pytest tests/ -m integration -q

# Specific file
pytest tests/test_recipe_merge.py -q

# Specific test class
pytest tests/test_admin_helpers.py::TestCategorize -q
```

### Pre-Commit Gate

```bash
# Fast gate — unit tests only
pytest tests/ -m unit -q --tb=short

# Full gate — all tests
pytest tests/ -q --tb=short
```

## File Organization

Test files mirror source structure and are split by responsibility:

| Test File | Tests | Marker |
|-----------|-------|--------|
| `test_admin_helpers.py` | Categorization, secrets detection, filenames, SHA256, manifest, duration, encryption | unit |
| `test_admin_backup.py` | Backup/restore/prune/list/inspect, PostgreSQL dump | integration |
| `test_recipe_merge.py` | DeepDiff merge, env merge, recursive merge, installation orchestration | unit |
| `test_recipe_io.py` | GitHub fetch, local resolution, summary, end-to-end apply, store resolution | integration |
| `test_vscode_proxy_helpers.py` | Model ID resolution, deduplication, entry building, reasoning effort | unit |
| `test_vscode_proxy_io.py` | Master key resolution, proxy URLs, health check, model fetch, alias/route loading | integration |
| `test_vscode_proxy_cmd.py` | Full CLI command flow with mocked network | integration |

### Naming Convention

- `test_<module>_helpers.py` — pure logic tests (unit)
- `test_<module>_io.py` — I/O-dependent tests (integration)
- `test_<module>_cmd.py` — CLI command tests (integration)
- `test_<module>.py` — single-responsibility module (either unit or integration, use `pytestmark`)

## Conventions

- All tests use `tmp_path` fixtures and `monkeypatch` for isolation.
- Never touch real `~/.codefreedom/` during tests.
- `conftest.py` sets `CODEFREEDOM_HOME` to a function-scoped `tmp_path` — each test gets its own directory.
- Test files use `pytestmark = pytest.mark.unit` or `pytest.mark.integration` at module level.
- Private functions (`_prefix`) are tested directly — this is intentional for internal API coverage.
- Mock at the lowest boundary: mock `_do_get` for HTTP tests, not `get_json` (which is imported locally).

## Adding New Tests

1. Determine if the test is unit or integration (see Decision Rule above).
2. Place in the appropriate file, or create a new one following the naming convention.
3. Add `pytestmark` if creating a new file.
4. Run `pytest tests/ -m unit -q` for unit tests or `pytest tests/ -m integration -q` for integration.
5. Ensure no regressions: `pytest tests/ -q --tb=short`.
