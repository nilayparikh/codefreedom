# Local (Native) Mode

Run code agents directly on your host — no Docker container, zero overhead.

## Usage

```bash
# Default native mode
codefreedom claude

# With a built-in profile (or custom)
codefreedom claude --profile bare

# Bypass the proxy, use native auth
codefreedom claude --native-models
```

## Prerequisites

```bash
npm install -g @anthropic-ai/claude-code
```

## How It Works

Native mode runs the code agent directly on the host. Profiles control model routing through the proxy:

- `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` from your profile point to the proxy
- Uses the host's `~/.claude` directory directly
- Use `--native-models` to strip proxy env vars and fall back to native auth

## When to Use Local vs Sandbox

| You want...                                  | Use                                 |
| -------------------------------------------- | ----------------------------------- |
| No overhead, direct host access              | Local (`codefreedom claude`)        |
| Container isolation, GPU passthrough         | [Sandbox](sandbox.md) (`--sandbox`) |
| Per-profile state isolation                  | Sandbox                             |
| Pass `--dangerously-skip-permissions` safely | Sandbox                             |

See [Sandbox Mode](sandbox.md) for GPU passthrough, image selection, and container lifecycle details.
