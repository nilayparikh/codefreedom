---
title: Agents
description: Code agents that CodeFreedom launches with zero-click proxy configuration.
---

Agents are the coding assistants CodeFreedom orchestrates. Each agent runs natively on your machine with automatic proxy configuration and model routing.

## Available Agents

| Agent | CLI Name | Alias | Description |
| --- | --- | --- | --- |
| [Claude Code](claude-code.md) | `claude-code` | `cc` | Anthropic's coding agent — native Claude models or proxy-routed |
| [MiMo Code](mimo-code.md) | `mimo-code` | `mc` | Xiaomi's coding agent — 0-click proxy config with model auto-discovery |
| [OpenCode](open-code.md) | `open-code` | `oc` | Terminal-native AI coding agent — 0-click proxy config with model auto-discovery |
| [Pi Code](pi-code.md) | `pi-code` | `pc` | Earendil's AI coding agent — extension-based dynamic model discovery |
| [Codex](codex-code.md) | `codex-code` | `cx` | OpenAI's coding agent — 0-click proxy config with model catalog generation |

## Quick Reference

```bash
cf run agent claude-code          # Launch Claude Code
cf run agent mimo-code            # Launch MiMo Code
cf run agent open-code            # Launch OpenCode
cf run agent pi-code              # Launch Pi Code
cf run agent codex-code           # Launch Codex
cf run agent list                 # List all available agents
```

Short aliases:

```bash
cf r ag cc                       # Claude Code
cf r ag mc                       # MiMo Code
cf r ag oc                       # OpenCode
cf r ag pc                       # Pi Code
cf r ag cx                       # Codex
cf r ag list                     # List agents
```

## How Agents Work

When you launch an agent, CodeFreedom:

1. **Loads your profile** — reads environment variables from `~/.codefreedom/profiles/<name>.yaml`
2. **Generates agent config** — auto-detects the proxy and builds the agent's config file with all available models
3. **Starts MCP tools** — ensures requested tool containers (Chrome, Web, GitHub) are running
4. **Launches the agent** natively on your host machine

## Common Flags

All agents share these flags:

| Flag | Description |
| --- | --- |
| `-p`, `--profile NAME` | Load a named profile (default: `default`) |
| `-l`, `--list-profiles` | List available profiles and exit |
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
