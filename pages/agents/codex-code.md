---
title: Codex
description: OpenAI's coding agent with 0-click proxy configuration and model catalog generation.
---

## Overview

Codex is OpenAI's terminal-native coding agent. CodeFreedom provides 0-click proxy configuration — it auto-detects the running LiteLLM proxy, fetches the model list, generates a complete `config.toml` with a custom model provider, and creates a model catalog with all available models.

**Binary:** `codex` (installed via `npm install -g @openai/codex`)

**Canonical name:** `codex-code` (alias: `cx`)

## Commands

```bash
cf run agent codex-code                    # Launch (native mode)
cf run agent codex-code --sandbox          # Launch (sandboxed)
cf run agent codex-code -p deepseek        # Launch with a profile
cf run agent codex-code config             # Print config.toml for standalone use
cf run agent codex-code status             # Show sandbox container status
cf run agent codex-code stop               # Stop running containers
```

Short:

```bash
cf r ag cx                               # Launch (native)
cf r ag cx --sandbox                     # Launch (sandboxed)
```

## Flags

| Flag | Description |
| --- | --- |
| `--sandbox` | Run inside a Docker container |
| `--run-as-me` | Run sandbox as host user (uid/gid match) |
| `--cuda` | Use CUDA sandbox image (NVIDIA GPUs) |
| `--rocm` | Use ROCm sandbox image (AMD GPUs) |
| `-p NAME`, `--profile NAME` | Load a named profile |
| `-l`, `--list-profiles` | List available profiles |

## How It Works

### 0-Click Proxy Configuration

CodeFreedom automates the entire Codex setup:

1. **Detects the proxy** at `PROXY_BASE_URL` (default: `http://localhost:4000`)
2. **Fetches model list** from the proxy's `/v1/models` endpoint
3. **Generates config** at `~/.codefreedom/codex-code/home/config.toml`
4. **Generates model catalog** at `~/.codefreedom/codex-code/home/model_catalog.json`
5. **Sets `CODEX_HOME`** env var to point at the generated config directory
6. **Launches Codex** — it loads all proxy models via the custom provider

No manual config editing required. Start the proxy, launch the agent, and all models are available.

### Native Mode

When launched natively, CodeFreedom:

1. Loads the full env chain (component-specific, shared, workspace, system)
2. Resolves the selected profile's environment variables
3. Generates `config.toml` and `model_catalog.json` with proxy model discovery
4. Launches `codex` with `CODEX_HOME` pointing to the generated config

### Sandbox Mode

Sandbox mode runs Codex inside a Docker container with:

- Isolated filesystem
- Mounted workspace directory
- Tool endpoints injected via MCP config
- Proxy configuration auto-generated inside the container

### Config Generation

The generated `config.toml` includes:

```toml
model = "gpt-5.5"
model_provider = "codefreedom"
model_reasoning_effort = "medium"
model_context_window = 131072
model_catalog_json = "~/.codefreedom/codex-code/home/model_catalog.json"

[model_providers.codefreedom]
name = "CodeFreedom Proxy"
base_url = "http://localhost:4000/v1"
wire_api = "responses"
```

### Model Catalog

The generated `model_catalog.json` includes all proxy models with metadata:

- Model ID, display name, description
- Reasoning levels (none, low, medium, high)
- Supported tools and input modalities
- Truncation policy and parallel tool call support

Custom models must be selected via `codex -m <model_name>` — the `/model` picker only shows built-in OpenAI models.

## Config Command

Print a proxy-resolved `config.toml` for standalone use outside CodeFreedom:

```bash
cf r ag cx config                       # Print to stdout
cf r ag cx config --out codex.toml      # Write to file
```

## MCP Tool Integration

Codex discovers MCP servers via `config.toml`. CodeFreedom registers tool endpoints in the `[mcp_servers]` section when launching the agent.

## Status and Lifecycle

```bash
cf r ag cx status                        # Check sandbox container status
cf r ag cx stop                          # Stop running containers
```

## Third-Party Notices

Codex is developed by OpenAI. CodeFreedom does not modify, patch, or bundle Codex. It only configures environment variables, generates config files, and launches the binary.
