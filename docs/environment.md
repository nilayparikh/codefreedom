# Environment Configuration

CodeFreedom uses a layered `.env` architecture for configuration. Settings cascade through five sources — later sources override earlier ones.

## Load Order

| Priority | Source | Purpose |
|----------|--------|---------|
| 1 (lowest) | `~/.codefreedom/.env` | Home config — database URLs, model aliases, proxy settings |
| 2 | `~/.codefreedom/.env.secrets` | Home secrets — API keys, passwords (skipped if missing) |
| 3 | `{workspace}/.env` | Per-project overrides — local model aliases, proxy tweaks |
| 4 | `{workspace}/.env.secrets` | Per-project secrets — project-specific API keys (skipped if missing) |
| 5 (highest) | System environment | Machine-level overrides — `export FOO=bar` always wins |

## File Conventions

| File | Contents | Git |
|------|----------|-----|
| `.env.example` | Template with all variables (commented) | Tracked — reference for new setups |
| `.env` | Active config | **Never commit** — add to `.gitignore` |
| `.env.secrets` | API keys, tokens, passwords | **Never commit** — add to `.gitignore` |

The `.env.example` file is tracked in git as a reference. Run `codefreedom --init` to create active `.env` and `.env.secrets` files in `~/.codefreedom/`.

## Variable Interpolation

Values support `${VAR}` references resolved from the current environment chain:

```bash
# Reference another variable
LITELLM_MASTER_KEY=${API_KEY}

# With a default fallback
CLAUDE_MODEL=${MODEL_NAME:-CodeFreedom/Flash}
```

References are resolved using the env chain (earlier sources first), so a variable defined in `.env` can be referenced by another variable in the same file.

## Per-Project Overrides

Create `.env` or `.env.secrets` in any workspace directory to override home config for that project:

```bash
# ~/projects/my-app/.env — routes this project to a local model
CLAUDE_MODEL="Local/Qwen3.6-27B"
ANTHROPIC_BASE_URL="http://localhost:8000/v1"
```

This is useful for:
- Pinning a project to a specific model
- Using local inference for one project while keeping cloud for others
- Project-specific proxy settings

## Custom Profile Location

Override the default profile file location:

```bash
export CODEFREEDOM_PROFILES_FILE="/path/to/custom/profiles.json"
```

## Security

- **`.env.secrets` separation.** API keys live in `.env.secrets`, never in `.env`. This makes it easy to apply different gitignore rules or share `.env` templates without exposing keys.
- **Sensitive value masking.** When loading profiles, values for keys containing `TOKEN`, `KEY`, `SECRET`, `AUTH`, or `PASSWORD` are masked in log output.
- **Workspace secrets are optional.** If `{workspace}/.env.secrets` does not exist, it is skipped silently — no error is raised.

## Common Variables

The full variable reference is in the bundled `.env.example` file. Key categories:

| Category | Variables |
|----------|-----------|
| Model aliases | `LITELLM_MODEL_ALIAS_ULTRA`, `LITELLM_MODEL_ALIAS_PRO`, `LITELLM_MODEL_ALIAS_FLASH` |
| Proxy | `LITELLM_PORT`, `LITELLM_BIND_HOST`, `LITELLM_LOG_LEVEL` |
| Providers | `DEEPSEEK_API_KEY`, `MICROSOFT_FOUNDRY_API_KEY`, `NVIDIA_API_KEY` |
| Sandbox | `CLAUDE_CODE_REGISTRY`, `CLAUDE_CODE_IMAGE_NAME`, `CLAUDE_CODE_IMAGE_TAG` |
| Profiles | `CODEFREEDOM_PROFILES_FILE` |

See [Proxy](proxy.md) for provider-specific configuration and [Sandbox Mode](claude-code/sandbox.md) for image selection.
