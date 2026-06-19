---
title: Pi Code
description: Earendil's AI coding agent with extension-based dynamic model discovery.
---

## Overview

Pi Code is Earendil's AI coding agent. CodeFreedom generates a TypeScript extension for dynamic model discovery, configures LSP servers, and launches Pi with zero manual configuration.

**Binary:** `pi` (installed via Pi's official installation)

**Canonical name:** `pi-code` (alias: `pc`)

## Commands

```bash
cf run agent pi-code                     # Launch (native mode)
cf run agent pi-code -p deepseek         # Launch with a profile
cf run agent pi-code --list-profiles     # List available profiles
```

Short:

```bash
cf r ag pc                               # Launch
```

## Flags

| Flag | Description |
| --- | --- |
| `-p NAME`, `--profile NAME` | Load a named profile |
| `-l`, `--list-profiles` | List available profiles |

## How It Works

### Extension-Based Config

CodeFreedom automates Pi Code setup via a TypeScript extension:

1. **Generates extension** at `<pi-agent-home>/extensions/codefreedom.ts`
2. **Extension registers a provider** using `pi.registerProvider()` for dynamic model discovery
3. **Fetches `/v1/model/info`** from the proxy for rich capabilities (vision, reasoning, costs)
4. **Configures `pi-mcp-adapter`** via `.mcp.json` for MCP tool support
5. **Launches Pi** with the extension loaded automatically

### Extension Details

The generated `codefreedom.ts` extension:

- Registers a custom provider with Pi's extension API
- Dynamically discovers models from the running proxy
- Provides model metadata: capabilities, pricing, context windows
- Refreshes the model list when the proxy restarts

### LSP Server Configuration

Pi Code supports Language Server Protocol (LSP) integration. CodeFreedom reads LSP server configuration from the profile and ensures the required servers are available:

```yaml
# In profile.yaml
lsp_servers:
  python: [pylsp]
  typescript: [typescript-language-server]
```

### MCP Tool Integration

Pi Code discovers MCP tools via `.mcp.json` in the workspace. CodeFreedom writes this file with all available tool endpoints when launching the agent.

### Lean Context Integration

CodeFreedom configures `lean-ctx` in Pi's agent home directory for persistent project knowledge across sessions. This enables Pi to recall project patterns, decisions, and code relationships.

## Native Mode

When launched natively, CodeFreedom:

1. Loads the full env chain (component-specific, shared, workspace, system)
2. Resolves the selected profile's environment variables
3. Generates the `codefreedom.ts` extension
4. Configures LSP servers and lean-ctx
5. Writes `.mcp.json` for tool discovery
6. Launches `pi` with all configuration in place

## Model Discovery

Pi Code's extension fetches model info from the proxy:

```text
GET /v1/model/info → capabilities, pricing, context windows
```

Models appear in Pi's model selector with full metadata — no manual model list configuration needed.

## Third-Party Notices

Pi Code is developed by Earendil. CodeFreedom does not modify, patch, or bundle Pi Code. It only generates extensions, configures environment variables, and launches the binary.
