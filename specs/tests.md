# Test Coverage

Test modules and coverage overview.

## Running Tests

```bash
python -m pytest tests/ -v                    # all tests
python -m pytest tests/test_admin.py -v       # specific file
python -m pytest tests/test_admin.py::TestBackup::test_basic_backup -v  # specific test
```

## Test Modules

| File | Coverage |
|------|----------|
| `test_admin.py` | Backup, restore, list, inspect, prune |
| `test_chrome.py` | Chrome tool container lifecycle |
| `test_deinit.py` | Full teardown, config removal |
| `test_doctor.py` | Environment diagnostics |
| `test_docker_utils.py` | Docker container lifecycle helpers |
| `test_env_loader.py` | `.env` parsing, chain precedence, `${VAR}` resolution |
| `test_github.py` | GitHub MCP tool lifecycle |
| `test_recipe.py` | Recipe system |
| `test_profiles.py` | Profile loading, inheritance |
| `test_proxy.py` | Path resolution, config validation |
| `test_reasoning_efforts_mapping.py` | Reasoning-efforts plugin |
| `test_vscode_claude.py` | VS Code Claude config generation |
| `test_vscode_proxy.py` | VS Code proxy config generation |
| `test_web.py` | Web (Camoufox) tool lifecycle |
| `test_web_bridge.py` | Web bridge integration |

## Conventions

- All tests use `tmp_path` fixtures and `monkeypatch` for path isolation.
- Never touch real `~/.codefreedom/` during tests.
- Test files mirror source structure: `tests/test_<module>.py`.
