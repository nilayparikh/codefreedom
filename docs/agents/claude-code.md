---
title: Claude Code
description: Anthropic's coding agent — native Claude models or proxy-routed via CodeFreedom.
---

## Overview

Claude Code is Anthropic's official coding agent. CodeFreedom launches it with automatic environment configuration, routing through your local proxy or directly to Anthropic's API.

**Binary:** `claude` (installed via `npm install -g @anthropic/claude-code`)

**Canonical name:** `claude-code` (alias: `cc`)

## Commands

```bash
cf run agent claude-code                    # Launch (native mode)
cf run agent claude-code --sandbox          # Launch (sandboxed)
cf run agent claude-code -p deepseek        # Launch with a profile
cf run agent claude-code config             # Print env vars for standalone use
```

Short:

```bash
cf r ag cc                                 # Launch (native)
cf r ag cc --sandbox                       # Launch (sandboxed)
```

## Flags

| Flag | Description |
| --- | --- |
| `--sandbox` | Run inside a Docker container |
| `--run-as-me` | Run sandbox as host user (uid/gid match) |
| `--cuda` | Use CUDA sandbox image (NVIDIA GPUs) |
| `--rocm` | Use ROCm sandbox image (AMD GPUs) |
| `--native-models` | Use native Anthropic models/auth (strips proxy env vars) |
| `--dangerously-skip-permissions` | Skip permission prompts (CI/non-interactive use) |
| `-p NAME`, `--profile NAME` | Load a named profile |
| `-l`, `--list-profiles` | List available profiles |

## How It Works

### Native Mode

When launched natively, CodeFreedom:

1. Loads the full env chain (component-specific, shared, workspace, system)
2. Resolves the selected profile's environment variables
3. Writes `.mcp.json` to the workspace for tool discovery
4. Launches `claude` with the resolved environment

Key environment variables set by CodeFreedom:

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_BASE_URL` | Points to your local proxy (`http://localhost:4000`) |
| `ANTHROPIC_AUTH_TOKEN` | Proxy authentication key |
| `CLAUDE_MODEL` | Default model from your profile |
| `IS_SANDBOX` | Whether running in sandbox mode |

### Sandbox Mode

Sandbox mode runs Claude Code inside a Docker container with:

- Isolated filesystem
- Mounted workspace directory
- Tool endpoints injected via MCP config
- Optional GPU acceleration (`--cuda`, `--rocm`)

### Native Models Mode

Use `--native-models` to bypass the proxy and use Anthropic's native `/login` authentication:

```bash
cf r ag cc --native-models
```

This strips `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, and `IS_SANDBOX` from the environment.

## Config Command

Print environment variables for standalone use outside CodeFreedom:

```bash
cf r ag cc config                       # Print to stdout (with confirmation)
cf r ag cc config --out claude.env      # Write to file
cf r ag cc config --powershell          # PowerShell format
```

## Third-Party Notices

Claude Code is developed by Anthropic, PBC. CodeFreedom does not modify, patch, or bundle Claude Code. It only configures environment variables and launches the binary.
