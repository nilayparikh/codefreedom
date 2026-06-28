---
title: MiMo Code
description: Xiaomi's coding agent with 0-click proxy configuration and model auto-discovery.
---

## Overview

MiMo Code is Xiaomi's terminal-native coding agent. CodeFreedom provides 0-click proxy configuration — it auto-detects the running LiteLLM proxy, fetches the model list, and generates a complete `mimocode.json` config with all available models.

**Binary:** `mimo` (installed via `npm install -g @mimo/mimo-code`)

**Canonical name:** `mimo-code` (alias: `mc`)

## Commands

```bash
cf run agent mimo-code                    # Launch
cf run agent mimo-code -p deepseek        # Launch with a profile
cf run agent mimo-code status             # Show proxy and config status
cf run agent mimo-code stop               # Stop the agent
```

Short:

```bash
cf r ag mc                               # Launch
```

## Flags

| Flag | Description |
| --- | --- |
| `-p NAME`, `--profile NAME` | Load a named profile |
| `-l`, `--list-profiles` | List available profiles |

## How It Works

### 0-Click Proxy Configuration

CodeFreedom automates the entire MiMo Code setup:

1. **Detects the proxy** at `PROXY_BASE_URL` (default: `http://localhost:4000` or remote URL from `proxy.remote_url`)
2. **Fetches model list** from the proxy's `/v1/models` endpoint
3. **Generates config** at `~/.codefreedom/mimo-code/mimocode.json`
4. **Sets `MIMOCODE_CONFIG`** env var to point at the generated config
5. **Launches MiMo** — it loads all proxy models as `codefreedom/<model-id>`

No manual config editing required. Start the proxy, launch the agent, and all models are available.

### Native Mode

When launched natively, CodeFreedom:

1. Loads the full env chain (component-specific, shared, workspace, system)
2. Resolves the selected profile's environment variables
3. Generates `mimocode.json` with proxy model discovery
4. Launches `mimo` with `MIMOCODE_CONFIG` pointing to the generated config

### Config Generation

The generated `mimocode.json` includes:

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

All models from the proxy appear as `codefreedom/<model-id>` in MiMo Code's model selector.

## MCP Tool Integration

MiMo Code discovers MCP tools via `_update_mimo_mcp()`, which writes tool configuration to MiMo's MCP config directory. Tools are automatically available when the agent starts.

## Status and Lifecycle

```bash
cf r ag mc status                        # Check proxy connection and config
cf r ag mc stop                          # Stop a running MiMo instance
```

## Third-Party Notices

MiMo Code is developed by Xiaomi. CodeFreedom does not modify, patch, or bundle MiMo Code. It only configures environment variables, generates config files, and launches the binary.
