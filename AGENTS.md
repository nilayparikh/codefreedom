# AGENTS.md — CodeFreedom Codebase Conventions

This file defines conventions that all AI agents and contributors MUST follow
when working on the CodeFreedom codebase.

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

- **Imports**: Group stdlib, then third-party, then local. One blank line between groups.
- **Type hints**: Use `from __future__ import annotations` at the top of every module.
- **No comments**: Do not add comments unless explicitly asked.
- **No emojis**: Never add emojis to code, output, or documentation unless the user requests it.
- **Error handling**: Only validate at system boundaries. Don't add defensive checks for internal code.

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

## Docker / PostgreSQL Conventions

- PG data: Docker named volume `codefreedom_pg_data` (not a bind-mount)
- PG backup: Docker named volume `codefreedom_pg_backup` (not a bind-mount); dump files are extracted via `docker cp` during `cf manage admin backup`
- Container user: root (no uid/gid mapping — simplest path across Windows, macOS, Linux)
- PG listens on localhost:5432 only (TCP, never exposed externally)

---

## CLI Conventions

- Short aliases: `cf s i` = `cf setup init`, `cf px` = `cf run proxy`, `cf cc` = `cf run agent claude-code`
- Recommended flow: `cf s i -pa <recipe>` (plan-and-apply with confirmation)
- Secrets are checked after apply using the full env chain (`.env.*.secrets` + `os.environ` + `CF_CLI_*` overrides)
- `.env.user` is auto-created on first apply if missing
