---
title: OpenCode
description: Terminal-native AI coding agent with 0-click proxy configuration and model auto-discovery.
---

## Overview

OpenCode is a terminal-native AI coding agent. CodeFreedom provides 0-click proxy configuration — it auto-detects the running LiteLLM proxy, fetches the model list, and generates a complete `opencode.json` config with all available models.

**Binary:** `opencode` (installed via official OpenCode distribution)

**Canonical name:** `open-code` (alias: `oc`)

## Commands

```bash
cf run agent open-code                    # Launch (native mode)
cf run agent open-code --sandbox          # Launch (sandboxed)
cf run agent open-code -p deepseek        # Launch with a profile
cf run agent open-code status             # Show proxy and config status
cf run agent open-code stop               # Stop the agent
```

Short:

```bash
cf r ag oc                               # Launch (native)
cf r ag oc --sandbox                     # Launch (sandboxed)
```

## Flags

| Flag | Description |
| --- | --- |
| `--sandbox` | Run inside a Docker container |
| `--run-as-me` | Run sandbox as host user (uid/gid match) |
| `-p NAME`, `--profile NAME` | Load a named profile |
| `-l`, `--list-profiles` | List available profiles |

## How It Works

### 0-Click Proxy Configuration

CodeFreedom automates the entire OpenCode setup:

1. **Detects the proxy** at `PROXY_BASE_URL` (default: `http://localhost:4000`)
2. **Fetches model list** from the proxy's `/v1/models` endpoint
3. **Generates config** at `~/.codefreedom/open-code/config/opencode.json`
4. **Sets `OPENCODE_CONFIG`** env var to point at the generated config
5. **Launches OpenCode** — it loads all proxy models as `codefreedom/<model-id>`

No manual config editing required. Start the proxy, launch the agent, and all models are available.

### Native Mode

When launched natively, CodeFreedom:

1. Loads the full env chain (component-specific, shared, workspace, system)
2. Resolves the selected profile's environment variables
3. Generates `opencode.json` with proxy model discovery
4. Launches `opencode` with `OPENCODE_CONFIG` pointing to the generated config

### Sandbox Mode

Sandbox mode runs OpenCode inside a Docker container with:

- Isolated filesystem
- Mounted workspace directory
- Tool endpoints injected via MCP config
- Proxy configuration auto-generated inside the container

### Config Generation

The generated `opencode.json` includes:

```json
{
  "provider": {
    "codefreedom": {
      "apiKey": "<proxy-key>",
      "models": {
        "codefreedom/gpt-4o": {},
        "codefreedom/deepseek-chat": {},
        "codefreedom/mimo-7b": {}
      }
    }
  }
}
```

All models from the proxy appear as `codefreedom/<model-id>` in OpenCode's model selector.

## MCP Tool Integration

OpenCode discovers MCP tools via `_update_opencode_mcp()`, which writes tool configuration to OpenCode's MCP config directory. Tools are automatically available when the agent starts.

## Status and Lifecycle

```bash
cf r ag oc status                        # Check proxy connection and config
cf r ag oc stop                          # Stop a running OpenCode instance
```

## Third-Party Notices

OpenCode is a third-party open-source project. CodeFreedom does not modify, patch, or bundle OpenCode. It only configures environment variables, generates config files, and launches the binary.
