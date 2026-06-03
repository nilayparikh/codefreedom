# Code Agents

Launch code agents with profile-based model routing through your LLM proxy.

> **No hacks.** CodeFreedom orchestrates code agents through their publicly
> documented interfaces — environment variables, CLI flags, and API endpoints.
> It does not patch, reverse-engineer, or tamper with any code agent.

## Quick Reference

```bash
codefreedom claude              # Native mode (default)
codefreedom claude --sandbox    # Docker sandbox
codefreedom claude --profile bare     # Pick a built-in profile
codefreedom claude --list-profiles    # List available profiles
codefreedom claude --stop       # Stop sandbox containers
codefreedom claude --status     # Show container status
codefreedom claude -p "question"  # One-shot prompt
```

Short aliases: `cf cc` is equivalent to `codefreedom claude`.

## Execution Modes

| Mode                                   | Command                        | Use When...                                    |
| -------------------------------------- | ------------------------------ | ---------------------------------------------- |
| [Local (Native)](claude-code/local.md) | `codefreedom claude`           | Running on your host, no isolation needed      |
| [Sandbox](claude-code/sandbox.md)      | `codefreedom claude --sandbox` | Isolated Docker container with GPU passthrough |

Both modes support `--profile` for model switching and `--native-models` to bypass the proxy and use native auth.

## Sandbox Images

Three pre-configured images (CUDA, ROCm, Ubuntu) on `docker.io/nilayparikh/codefreedom`. (Also available on `ghcr.io/nilayparikh/codefreedom` as a mirror.)
See [Sandbox Mode → Available Images](claude-code/sandbox.md#available-images) for the full tag reference and Dockerfile examples.

## Profile System

Profiles control which model a code agent uses by setting environment variables. All profiles live in `~/.codefreedom/profiles/claude-code.json`.

### Built-in Profiles

| Profile   | Model               | Description                            |
| --------- | ------------------- | -------------------------------------- |
| `default` | `CodeFreedom/Flash` | General purpose — routes through proxy |
| `bare`    | _(default)_         | Minimal — no model aliases             |

Custom profiles such as `pro` or `ultra` are not bundled by default — create them in the profiles file. The model aliases (`CodeFreedom/Flash`, `CodeFreedom/Pro`, `CodeFreedom/Ultra`) are defined in the [proxy configuration](proxy.md#model-aliases), not in profiles.

### Creating Custom Profiles

Edit `~/.codefreedom/profiles/claude-code.json`:

```json
{
  "profiles": {
    "my-profile": {
      "description": "Custom profile — overrides model and endpoint",
      "env": {
        "CLAUDE_MODEL": "CodeFreedom/Ultra",
        "ANTHROPIC_BASE_URL": "http://localhost:4000"
      }
    }
  }
}
```

Custom profiles automatically inherit from `default` — only set what differs.

### Mode-Specific Overrides

Profiles can set different environment variables for sandbox vs local mode using `sandbox.env` and `local.env` keys:

```json
{
  "profiles": {
    "dev": {
      "description": "Uses cloud model locally, local model in sandbox",
      "env": {
        "ANTHROPIC_BASE_URL": "http://localhost:4000"
      },
      "local": {
        "env": {
          "CLAUDE_MODEL": "CodeFreedom/Pro"
        }
      },
      "sandbox": {
        "env": {
          "CLAUDE_MODEL": "Local/Qwen3.6-27B"
        }
      }
    }
  }
}
```

Mode-specific overrides inherit from `default` the same way base env does — if `default` sets `sandbox.env`, your profile inherits those values and can override them.

### Variable Interpolation

Profile values support `${VAR}` references, resolved from the [environment chain](environment.md):

```json
{
  "profiles": {
    "custom": {
      "env": {
        "CLAUDE_MODEL": "${MODEL_NAME:-CodeFreedom/Flash}",
        "ANTHROPIC_BASE_URL": "${PROXY_URL:-http://localhost:4000}"
      }
    }
  }
}
```

The `:-default` syntax provides a fallback if the variable is not set.

### Sandbox Images per Profile

Set custom sandbox images for a profile — these are GPU-specific Docker image references:

```json
{
  "profiles": {
    "gpu-work": {
      "description": "CUDA sandbox for GPU workloads",
      "sandbox_images": {
        "default": "docker.io/nilayparikh/codefreedom:latest",
        "cuda": "docker.io/nilayparikh/codefreedom:cuda-latest",
        "rocm": "docker.io/nilayparikh/codefreedom:rocm-latest"
      },
      "env": {
        "CLAUDE_MODEL": "CodeFreedom/Pro"
      }
    }
  }
}
```

Child profiles inherit `sandbox_images` from `default` and can override individual entries. If `--cuda` or `--rocm` is passed, the matching key is used; otherwise `default` is used. Falls back to environment variables (`CLAUDE_CODE_REGISTRY`, `CLAUDE_CODE_IMAGE_NAME`, `CLAUDE_CODE_IMAGE_TAG`).

### Listing Profiles

```bash
codefreedom claude --list-profiles
```

Output shows each profile, its inheritance, and which environment variables it sets:

```
[PROFILES] Available profiles (~/.codefreedom/profiles/claude-code.json):

  bare
    Minimal — no model aliases
    (standalone)

  default
    General purpose — routes through proxy
    (standalone)
    sets: ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, CLAUDE_MODEL
    sandbox: CLAUDE_CODE_IMAGE_TAG
```

### Custom Profile Location

Override the default profile file location:

```bash
export CODEFREEDOM_PROFILES_FILE="/path/to/custom/profiles.json"
```

A JSON Schema is provided at `~/.codefreedom/profiles/claude-code.schema.json` for editor validation.
