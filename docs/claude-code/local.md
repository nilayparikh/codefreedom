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

## VS Code Settings

The [Claude Code VS Code extension](https://marketplace.visualstudio.com/items?itemName=Anthropic.claude-code)
runs the same `claude` CLI inside VS Code. Generate a `settings.json`
fragment that mirrors your local profile so the extension picks up the
same routing, model, and feature flags:

```bash
# Default profile
codefreedom vscode claude config

# A specific profile
codefreedom vscode claude config --profile ultra

# Override the proxy host/port (e.g. when VS Code runs on a different
# machine than the proxy)
codefreedom vscode claude config --host proxy.lan --port 4000

# Write to a file instead of stdout
codefreedom vscode claude config --out /tmp/cf-fragment.json
```

The generated fragment contains the full env array, but **secret values
are replaced with `${env:VARNAME}` references** using the same env var
name. The resolved secret value is never written to disk — VS Code
substitutes the real value from your system environment at runtime.
See the [Secret Management section in VS Code docs](../../vscode.md#secret-management)
for the rationale and how to set the referenced env vars.
