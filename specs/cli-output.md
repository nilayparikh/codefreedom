# CLI Output Standards

All CodeFreedom CLI modules must follow these conventions for user-facing output.

## 1. Output Streams

| Stream     | Use For                                                          | Function   |
| ---------- | ---------------------------------------------------------------- | ---------- |
| **stderr** | All status, progress, warnings, errors                           | `eprint()` |
| **stdout** | Machine-readable output only (URLs, config fragments, list data) | `print()`  |

Machine-readable output includes:

- `cf run tools chrome url` — CDP debug URL
- `cf vscode claude config` — VS Code settings fragment
- `cf vscode proxy config` — VS Code proxy config fragment
- `cf r ag cc config` — resolved env vars

Everything else (progress messages, warnings, errors, section headers) goes to stderr via `eprint()`.

## 2. Message Prefixes

All `eprint()` messages must use an uppercase `[COMPONENT]` prefix. No nested prefixes.

| Component          | Prefix                            |
| ------------------ | --------------------------------- |
| Chrome tool        | `[CHROME]`                        |
| Web tool           | `[WEB]`                           |
| GitHub MCP tool    | `[GITHUB]`                        |
| Web bridge tool    | `[WEB-BRIDGE]`                    |
| Tools manager      | `[TOOLS]`                         |
| Proxy              | `[PROXY]`                         |
| Admin/backup       | `[ADMIN]`                         |
| Deinit             | `[DEINIT]`                        |
| Doctor             | `[DOCTOR]`                        |
| Recipe             | `[RECIPE]`                        |
| Update             | `[UPDATE]`                        |
| VS Code            | `[VSCODE]`                        |
| Launcher/sandbox   | `[SANDBOX]`                       |
| Environment loader | `[ENV]`                           |
| Profile loader     | `[PROFILE]`                       |
| MCP                | `[MCP]`                           |
| Docker utils       | Use the caller's component prefix |

**No nested prefixes.** Instead of `[proxy] [OK]` or `[backup] [WARN]`, write:

```
[PROXY] Proxy started at http://localhost:4000.
[ADMIN] Warning: pg_dump failed (exit code 1).
```

The message text conveys severity — no need for a separate `[OK]`/`[WARN]`/`[FAIL]` tag.

## 3. Punctuation

All messages end with a period (`.`). This applies to:

- Status messages: `[CHROME] Container started.`
- Error messages: `[ERROR] Docker not found.`
- Warning messages: `[PROXY] Warning: image missing.`
- Info messages: `[ENV] Loaded shared config from /path/to/.env.`

Exceptions:

- URLs and paths shown inline: `[CHROME] CDP debug URL: http://127.0.0.1:9222.`
- Continuation lines that are part of a list (no period needed on list items)

## 4. Message Structure

```
[COMPONENT] Action completed.
[COMPONENT] Using data dir: /path/to/dir.
[COMPONENT] Container 'name' is already running.
[COMPONENT] Container 'name' exists but is not running.
[COMPONENT] No container found.
   Use: cf run tools start
```

For multi-line output after an action:

```
[CHROME] Container started.
   CDP debug URL: http://127.0.0.1:9222
   MCP endpoint:  http://127.0.0.1:9223/mcp
```

Indented continuation lines use 3 spaces.

## 5. Error Messages

- `[ERROR]` prefix for fatal errors (return code 1).
- `Warning:` text within the component prefix for non-fatal issues.
- Always include a suggestion for how to fix the error.

```
[ERROR] Docker not found.
   Install Docker: https://docs.docker.com/get-docker/
```

## 6. Return Codes

| Code | Meaning                                                 |
| ---- | ------------------------------------------------------- |
| 0    | Success                                                 |
| 1    | Recoverable error (missing config, Docker failed, etc.) |
| 2+   | Reserved for future use                                 |

All CLI subcommand `run()` functions return an `int` exit code.

## 7. Doctor Output

Doctor uses `print()` to stdout for its structured output (section headers, check results, summary). This is intentional — doctor output is designed to be piped/grepped by users.

## 8. Interactive Prompts

Interactive prompts (e.g., `input("Continue? [y/N]: ")`) use `print()` for the prompt text since they go to the terminal. The surrounding notices and banners use `eprint()`.
