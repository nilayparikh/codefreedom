# AGENTS.md — CodeFreedom Codebase Conventions

This file defines conventions that all AI agents and contributors MUST follow
when working on the CodeFreedom codebase.

---

## Acceptance Criteria

Every code change must pass these automated checks before commit. They encode
the conventions below into verifiable gates.

### 1. Lint — `ruff check src/ tests/`

| Rule | Convention enforced |
|------|---------------------|
| `F401` | No unused imports |
| `F811` | No redefined unused names |
| `E` | PEP 8 style (line length, whitespace, syntax) |
| `W` | Warning-level PEP 8 issues |
| `I` | Import sorting (stdlib → third-party → local) |

Additional ruff rules recommended for this project:

```toml
[tool.ruff.lint]
select = ["F", "E", "W", "I", "T201", "UP"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["T201"]
```

| Rule | Convention enforced |
|------|---------------------|
| `T201` | No bare `print()` — use `tag()` for user-facing output |
| `UP` | Python upgrade suggestions (modern syntax) |

### 2. Type-check — `mypy src/ --ignore-missing-imports`

Catches type errors, missing return statements, and incorrect signatures.

### 3. Tests — `pytest tests/ -q --tb=short`

All tests must pass. Pre-existing failures are documented in MEMORY.md.

**Test categories (markers):**

| Marker | What | Speed | When to run |
|--------|------|-------|-------------|
| `unit` | Pure logic, no I/O | ~2s | Always (pre-commit gate) |
| `integration` | Filesystem, Docker, network | ~10s | Full validation |

**Acceptance criteria for any code change:**

```bash
# Fast gate — always run this
pytest tests/ -m unit -q --tb=short

# Full gate — run before commit
pytest tests/ -q --tb=short

# Scoped to changed module
pytest tests/test_<module>_helpers.py tests/test_<module>_io.py -q --tb=short
```

**When adding new tests:**

- Pure logic → `test_<module>_helpers.py` with `pytestmark = pytest.mark.unit`
- I/O, Docker, subprocess → `test_<module>_io.py` with `pytestmark = pytest.mark.integration`
- CLI commands → `test_<module>_cmd.py` with `pytestmark = pytest.mark.integration`
- See `specs/tests.md` for full architecture and decision rules

### 4. Convention-Specific Gates

These are not yet automated as lint rules but MUST be verified manually or via
the `/validate` command. They are candidates for custom ruff rules or pytest checks.

| Convention | Verification | Status |
|-----------|--------------|--------|
| All `print()`/`eprint()` use `tag()` | `grep -rn 'print(f"\[' src/` returns empty | **VIOLATION**: `core/profiles.py` has bare `[ERROR]`, `[WARN]`, `[PROFILE]` |
| `read_text()`/`write_text()` use `encoding="utf-8"` | `grep -rn 'read_text()\|write_text()' src/ \| grep -v encoding` returns empty | **VIOLATION**: `recipe/plan.py:326` missing encoding |
| `from __future__ import annotations` in all modules | 50/50 modules — 100% compliant | **PASS** |
| Agent names are hyphenated | `grep -rn '"claude"\|"mimo"\|"opencode"' src/ \| grep -v shutil.which` returns empty | **PASS** (bare names only in `shutil.which()` for binary lookup) |
| No comments unless asked | Manual review | N/A |
| No emojis in code/output | Manual review | N/A |

---

## Color-Coded Tag Policy

### The Rule

ALL user-facing `print()` / `eprint()` feedback messages MUST use the `tag()`
helper from `codefreedom.log` for their bracket prefix. Tags MUST be in CAPS.

```python
from codefreedom.log import tag

# CORRECT
eprint(f"{tag('PROXY')} Proxy started at http://localhost:{port}")
print(f"{tag('RECIPE')} Plan applied — {count} file(s) updated.")

# WRONG — no color, inconsistent
eprint("[PROXY] Proxy started")
print("[recipe] Plan applied")
```

### Tag Color Map

| Color          | Tags                                                                                                                                                                                               | When to Use                                          |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **Green**      | `OK`, `SET`, `SAME`, `CREATE`, `MKDIR`, `BACKUP`, `PRUNE`, `KEEP`                                                                                                                                  | Success, completion, no action needed                |
| **Red + Bold** | `FAIL`, `MISSING`, `ERROR`                                                                                                                                                                         | Errors, missing required items, hard failures        |
| **Yellow**     | `WARN`, `SKIP`, `DEINIT`, `ADMIN`, `DELETE`                                                                                                                                                        | Warnings, destructive actions, non-critical issues   |
| **Cyan**       | `PLAN`, `SECRETS`, `RECIPE`, `STORE`, `PROXY`, `RESTORE`, `VSCODE`, `TOOLS`, `AGENT`, `DOCTOR`, `SANDBOX`, `MCP`, `FETCH`, `INFO`, `ENV`, `GPU`, `IMAGE`, `CONTAINER`, `NATIVE`, `CONFIG`, `LOCAL` | Section labels, informational status, component tags |
| **Dim**        | Any tag not in the above sets                                                                                                                                                                      | Fallback for unclassified tags                       |

### When to Use Tags

- **Always** on feedback messages (status updates, confirmations, warnings, errors)
- **Always** on user-facing instructions or next-step guidance
- **Not required** on: tabular data rows (inside a tagged context), blank separator
  lines, debug output (use `eprint()` for debug), continuation lines after a tagged line

### Python 3.10 Compatibility

Nested quotes in f-strings are NOT allowed (Python 3.12+ feature). Always use
single quotes inside `tag()` when the f-string uses double quotes:

```python
# CORRECT — single quotes inside double-quoted f-string
eprint(f"{tag('PROXY')} Message here")

# WRONG — syntax error on Python 3.10
eprint(f"{tag("PROXY")} Message here")
```

### Adding New Tags

When adding a new component tag:

1. Add the tag name to the appropriate `_TAG_*` frozenset in `src/codefreedom/log.py`
2. Follow the color semantics above (green = success, red = error, yellow = warning, cyan = info)
3. Use the tag consistently in all print/eprint statements in that component

---

## File-Level Conventions

### Python Files

- **Imports**: Group stdlib, then third-party, then local. One blank line between groups. Enforced by ruff `I` rule.
- **Type hints**: Use `from __future__ import annotations` at the top of every module.
- **No comments**: Do not add comments unless explicitly asked.
- **No emojis**: Never add emojis to code, output, or documentation unless the user requests it.
- **Error handling**: Only validate at system boundaries. Don't add defensive checks for internal code.
- **Encoding**: Always pass `encoding="utf-8"` to `read_text()` and `write_text()`. On Windows, the default encoding is `cp1252`, not UTF-8.

### YAML Files (docker-compose, recipe.yaml)

- Tags in YAML comments should be CAPS when they refer to CLI output tags.
- Use named Docker volumes (not bind-mounts) for data directories to avoid
  cross-platform permission issues. Bind-mounts are OK for user-accessible paths
  (e.g., backup directories).

### Documentation

- Tags referenced in docs should be CAPS: `[PLAN]`, `[RECIPE]`, `[PROXY]`, etc.
- CLI flags: use `--long-form` and `-s` (short) consistently.
- When documenting commands, show the recommended `-pa` (plan-and-apply) flow first.

---

## Agent Naming Convention

All agents use **hyphenated** forms. Never use single-word names.

| Canonical name | Aliases | Docker image | Directory on disk |
|---------------|---------|--------------|-------------------|
| `claude-code` | `cc` | `codefreedom:claude-code-latest` | `claude-code/` |
| `mimo-code` | `mc` | `codefreedom:mimo-code-latest` | `mimo-code/` |
| `open-code` | `oc` | `codefreedom:open-code-latest` | `open-code/` |

Bare names (`claude`, `mimo`, `opencode`) are invalid and will fail.

Note: `shutil.which("claude")` is correct — it looks up the actual binary name on PATH, not the CodeFreedom canonical name.

---

## Environment Variable Chain

Secrets and config resolve through a priority chain. Higher tiers win.

| Priority | Source | Example |
|----------|--------|---------|
| 1 (highest) | `CF_CLI_*` env vars | `CF_CLI_OPENAI_API_KEY` |
| 2 | `os.environ` | `OPENAI_API_KEY` |
| 3 | `.env.user` | `~/.codefreedom/.env.user` |
| 4 (lowest) | `.env.*.secrets` files | `~/.codefreedom/.env.proxy.secrets` |

The `_resolve_secret()` function in `recipe/apply.py` implements this chain.
The `load_tool_profile()` function in `core/profiles.py` uses a similar chain for tool config.

`GH_TOKEN` is always derived from `GITHUB_PERSONAL_ACCESS_TOKEN` — only one GitHub secret needs to be set.

---

## Docker / PostgreSQL Conventions

- **Multi-arch**: All images build for `linux/amd64` + `linux/arm64` except ROCm (amd64-only).
- **Image versions**: All Dockerfiles use `ARG IMAGE_VERSION=1.0.0`.
- **PG data**: Docker named volume `codefreedom_pg_data` (not a bind-mount).
- **PG backup**: Docker named volume `codefreedom_pg_backup` (not a bind-mount).
- **Container user**: root (no uid/gid mapping — simplest path across platforms).
- **PG listens**: localhost:5432 only (TCP, never exposed externally).
- **Cosign**: Use `cosign-sign` to sign, `cosign-verify` to verify. Using verify to sign fails with "no signatures found".

---

## Recipe Conventions

Three recipe directories share structure but have independent copies:

- `_default` — base recipe (no local providers)
- `costeffective-coding` — full recipe (all providers)
- `costeffective-coding-with-local` — recipe without local providers

**Shared across recipes** (must be identical):

- `scripts/setup-secrets.sh` and `scripts/setup-secrets.ps1`

**Recipe-specific** (do NOT blindly copy):

- `recipe.yaml` (different `required_secrets`, `config_vars`)
- `proxy/config/providers/*.yaml` (provider configs differ)
- `.env.*.secrets` (different secret placeholders)

When fixing a script in one recipe, apply the same fix to all 3 recipes.

---

## CLI Conventions

- Short aliases: `cf s i` = `cf setup init`, `cf r px` = `cf run proxy`, `cf r ag cc` = `cf run agent claude-code`
- Admin shortcuts: `cf m ad bu` = `backup`, `cf m ad res` = `restore`, `cf m ad ins` = `inspect`, `cf m ad pr` = `prune`
- Recommended flow: `cf s i -pa <recipe>` (plan-and-apply with confirmation)
- Secrets are checked after apply using the full env chain (`.env.*.secrets` + `os.environ` + `CF_CLI_*` overrides)
- `.env.user` is auto-created on first apply if missing
- Pre-commit checks: `ruff check` + `mypy` + `pytest` before every commit

---

## Pre-Commit Validation

Every commit must pass all three checks:

```bash
ruff check src/ tests/                    # lint
mypy src/ --ignore-missing-imports        # type-check
pytest tests/ -q --tb=short               # tests
```

Use the `/validate` command for a quick single-pass run. For single-file changes, scope ruff/mypy to that file first, then run the full pytest suite.

### Quick Validation Commands

```bash
# Full pipeline
ruff check src/ tests/ && mypy src/ --ignore-missing-imports && pytest tests/ -q --tb=short

# Unit tests only (fast gate)
pytest tests/ -m unit -q --tb=short

# Single file
ruff check src/codefreedom/cli/mimo.py && mypy src/codefreedom/cli/mimo.py

# Convention checks (manual)
grep -rn 'print(f"\[' src/codefreedom/     # bare tags without tag()
grep -rn 'read_text()' src/codefreedom/    # missing encoding
grep -rn 'write_text(' src/codefreedom/    # missing encoding
```
