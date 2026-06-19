---
title: Agents
description: Code agents that CodeFreedom launches with zero-click proxy configuration.
---

Agents are the coding assistants CodeFreedom orchestrates. Each agent runs either natively on your machine or inside a sandboxed Docker container, with automatic proxy configuration and model routing.

## Available Agents

| Agent | CLI Name | Alias | Description |
| --- | --- | --- | --- |
| [Claude Code](claude-code.md) | `claude-code` | `cc` | Anthropic's coding agent — native Claude models or proxy-routed |
| [MiMo Code](mimo-code.md) | `mimo-code` | `mc` | Xiaomi's coding agent — 0-click proxy config with model auto-discovery |
| [OpenCode](open-code.md) | `open-code` | `oc` | Terminal-native AI coding agent — 0-click proxy config with model auto-discovery |
| [Pi Code](pi-code.md) | `pi-code` | `pc` | Earendil's AI coding agent — extension-based dynamic model discovery |

## Quick Reference

```bash
cf run agent claude-code          # Launch Claude Code
cf run agent mimo-code            # Launch MiMo Code
cf run agent open-code            # Launch OpenCode
cf run agent pi-code              # Launch Pi Code
cf run agent list                 # List all available agents
```

Short aliases:

```bash
cf r ag cc                       # Claude Code
cf r ag mc                       # MiMo Code
cf r ag oc                       # OpenCode
cf r ag pc                       # Pi Code
cf r ag list                     # List agents
```

## How Agents Work

When you launch an agent, CodeFreedom:

1. **Loads your profile** — reads environment variables from `~/.codefreedom/profiles/<name>.yaml`
2. **Generates agent config** — auto-detects the proxy and builds the agent's config file with all available models
3. **Starts MCP tools** — ensures requested tool containers (Chrome, Web, GitHub) are running
4. **Launches the agent** — either natively or in a sandboxed Docker container

### Native vs Sandbox Mode

| Mode | Flag | Description |
| --- | --- | --- |
| Native | *(default)* | Runs directly on your host machine |
| Sandbox | `--sandbox` | Runs inside an isolated Docker container |

Sandbox mode is recommended for untrusted code. Native mode is simpler and has no container overhead.

### GPU Support

Sandbox mode supports GPU acceleration:

```bash
cf r ag cc --sandbox --cuda      # NVIDIA GPU (CUDA)
cf r ag cc --sandbox --rocm      # AMD GPU (ROCm)
```

## Common Flags

All agents share these flags:

| Flag | Description |
| --- | --- |
| `-p`, `--profile NAME` | Load a named profile (default: `default`) |
| `-l`, `--list-profiles` | List available profiles and exit |
| `--sandbox` | Run inside a Docker container |
| `--run-as-me` | Run sandbox as host user (uid/gid match) |
| `-- <args>` | Forward arguments to the agent |

## Profiles

Each agent reads its configuration from a profile. Profiles define which model, provider, and environment variables the agent uses.

```bash
cf r ag cc -p deepseek           # Use the 'deepseek' profile
cf r ag mc -p costeffective      # Use the 'costeffective' profile
```

See [Recipes](../recipes/index.md) for pre-configured profiles.

## Tool Integration

Agents connect to MCP tools automatically when launched. Tools are persistent Docker containers — start once, use from any agent session.

```bash
cf run tools start                # Start all tools
cf r ag cc                       # Launch agent — tools are auto-connected
```

See [Tools](../tools/index.md) for available tools and configuration.
