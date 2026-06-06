# Environment Configuration

CodeFreedom uses a **4-tier precedence chain** for `.env` configuration. Later tiers override earlier ones.

## Load Order by Component

### `codefreedom claude` (7 files, 4 tiers)

| Tier | Priority  | Source                               | Purpose                                                   |
| ---- | --------- | ------------------------------------ | --------------------------------------------------------- |
| 1    | Component | `~/.codefreedom/.env.claude`         | Claude Code agent config                                  |
| 1    | Component | `~/.codefreedom/.env.claude.secrets` | Claude Code secrets                                       |
| 2    | Shared    | `~/.codefreedom/.env`                | Shared config                                             |
| 2    | Shared    | `~/.codefreedom/.env.secrets`        | Shared secrets                                            |
| 3    | Workspace | `{workspace}/.env`                   | Per-project overrides — local model aliases, proxy tweaks |
| 3    | Workspace | `{workspace}/.env.secrets`           | Per-project secrets — project-specific API keys           |
| 4    | System    | System environment                   | Machine-level overrides — `export FOO=bar` always wins    |

### `codefreedom proxy` (7 files, 4 tiers)

| Tier | Priority  | Source                              | Purpose                                                        |
| ---- | --------- | ----------------------------------- | -------------------------------------------------------------- |
| 1    | Component | `~/.codefreedom/.env.proxy`         | Proxy config — database URLs, model aliases, provider settings |
| 1    | Component | `~/.codefreedom/.env.proxy.secrets` | Proxy secrets — provider API keys                              |
| 2    | Shared    | `~/.codefreedom/.env`               | Shared config                                                  |
| 2    | Shared    | `~/.codefreedom/.env.secrets`       | Shared secrets                                                 |
| 3    | Workspace | `{workspace}/.env`                  | Per-project overrides                                          |
| 3    | Workspace | `{workspace}/.env.secrets`          | Per-project secrets                                            |
| 4    | System    | System environment                  | Machine-level overrides — always wins                          |

### `codefreedom tools` (chrome, web) (5 files, 3 tiers)

| Tier | Priority  | Source                        | Purpose                               |
| ---- | --------- | ----------------------------- | ------------------------------------- |
| 2    | Shared    | `~/.codefreedom/.env`         | Shared config                         |
| 2    | Shared    | `~/.codefreedom/.env.secrets` | Shared secrets                        |
| 3    | Workspace | `{workspace}/.env`            | Per-project overrides                 |
| 3    | Workspace | `{workspace}/.env.secrets`    | Per-project secrets                   |
| 4    | System    | System environment            | Machine-level overrides — always wins |

> **Missing files are silently skipped.** No warning is emitted for any missing `.env` file.

## File Conventions

| File                          | Contents                                     | Git              |
| ----------------------------- | -------------------------------------------- | ---------------- |
| `.env.claude.example`         | Template for Claude Code vars (commented)    | Tracked          |
| `.env.claude.secrets.example` | Template for Claude Code secrets (commented) | Tracked          |
| `.env.claude`                 | Active Claude Code config                    | **Never commit** |
| `.env.claude.secrets`         | Active Claude Code secrets                   | **Never commit** |
| `.env.proxy.example`          | Template for proxy vars (commented)          | Tracked          |
| `.env.proxy.secrets.example`  | Template for proxy secrets (commented)       | Tracked          |
| `.env.proxy`                  | Active proxy config                          | **Never commit** |
| `.env.proxy.secrets`          | Active proxy secrets                         | **Never commit** |

Run the relevant init command to create active files:

```bash
codefreedom claude init  # creates ~/.codefreedom/.env.claude + .env.claude.secrets
codefreedom proxy init   # creates ~/.codefreedom/.env.proxy + .env.proxy.secrets
```

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

See [Code Agents → Profile System](../guides/agents.md#profile-system) for details.

## Security

- **`.env.secrets` separation.** API keys live in `.env.secrets`, never in `.env`. This makes it easy to apply different gitignore rules or share `.env` templates without exposing keys.
- **Sensitive value masking.** When loading profiles, values for keys containing `TOKEN`, `KEY`, `SECRET`, `AUTH`, or `PASSWORD` are masked in log output.
- **Workspace secrets are optional.** If `{workspace}/.env.secrets` does not exist, it is skipped silently — no error is raised.

## Common Variables

The full variable reference is in the bundled example files:

| File                         | Variables                                                                                                                           |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `.env.claude.example`        | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL`, `CLAUDE_CODE_COLUMNS`, `CLAUDE_CODE_LINES`                         |
| `.env.proxy.example`         | Model aliases (`LITELLM_MODEL_ALIAS_*`), retry settings, privacy flags, provider base URLs                                          |
| `.env.proxy.secrets.example` | `LITELLM_MASTER_KEY`, provider API keys (`DEEPSEEK_API_KEY`, `MICROSOFT_FOUNDRY_API_KEY`, `NVIDIA_API_KEY`, `OPENCODE_ZEN_API_KEY`) |
| `CODEFREEDOM_PROFILES_FILE`  | Override profile file location (system env)                                                                                         |

> **Note:** Variables like `LITELLM_PORT`, `LITELLM_LOG_LEVEL`, and `LITELLM_IMAGE` in `.env.proxy.example` are read by the proxy container at startup. `--port` and `--host` on `codefreedom proxy start` override `LITELLM_PORT` and `LITELLM_BIND_HOST` for that run only (they do not edit `.env.proxy`).

See [Proxy](proxy/index.md) for provider-specific configuration and [Sandbox Mode](../guides/sandbox.md) for image selection.
