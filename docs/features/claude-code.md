---
title: Agents
description: Launch coding agents with profile-based model routing, sandbox isolation, and GPU support.
---

Launch coding agents through CodeFreedom. Switch models, isolate environments, use GPUs — all with flags.

## Available Agents

| Agent | Full name | Alias | Description |
| ------- | --------- | ----- | ----------- |
| Claude Code | `claude-code` | `cc` | Anthropic's coding agent |
| MiMo Code | `mimo-code` | `mc` | Xiaomi's coding agent |
| OpenCode | `open-code` | `oc` | Terminal-native AI coding agent |

List available agents:

```bash
cf run agent list
# or
cf r ag list
```

## Basic Usage

```bash
# Full commands
cf run agent claude-code              # Local mode (default)
cf run agent claude-code --sandbox    # Docker sandbox
cf run agent claude-code --profile bare     # Pick a profile
cf run agent claude-code --list-profiles    # See what's available

# Short aliases
cf r ag cc                            # Same as above
cf r ag cc --sandbox                  # Sandbox mode
cf r ag cc -p bare                    # Pick a profile
cf r ag cc -l                         # List profiles
```

## Profiles

Profiles define which AI model your agent uses. Each profile maps to a different model in your proxy config.

```bash
# Switch models
cf run agent claude-code --profile bare      # DeepSeek R1 (fast, free)
cf run agent claude-code --profile air       # DeepSeek V3 (balanced)
cf run agent claude-code --profile ultra     # Claude Opus (strongest)
cf run agent claude-code --profile local     # Local Qwen3.6-27B

# Short form
cf r ag cc -p bare
cf r ag cc -p air
cf r ag cc -p ultra
cf r ag cc -p local
```

### Default Profile

If you don't specify `--profile`, the agent uses the `default` profile.

### Listing Profiles

```bash
cf run agent claude-code --list-profiles
# or
cf r ag cc -l
```

## Sandbox Mode

Run agents in isolated Docker containers. Clean environment, no host pollution.

```bash
# Basic sandbox
cf run agent claude-code --sandbox
# or
cf r ag cc --sandbox

# Sandbox with GPU
cf run agent claude-code --sandbox --gpu
# or
cf r ag cc --sandbox --gpu

# Sandbox with specific image
cf run agent claude-code --sandbox --image ubuntu:24.04
# or
cf r ag cc --sandbox --image ubuntu:24.04

# Sandbox with volume mount
cf run agent claude-code --sandbox --volume /path/on/host:/path/in/container
# or
cf r ag cc --sandbox --volume /path/on/host:/path/in/container
```

### GPU Support

```bash
# Auto-detect GPU
cf run agent claude-code --sandbox --gpu

# Force CUDA
cf run agent claude-code --sandbox --gpu --gpu-type cuda

# Force ROCm
cf run agent claude-code --sandbox --gpu --gpu-type rocm
```

### Sandbox Options

| Flag | Short | Description |
| ---- | ----- | ----------- |
| `--sandbox` | — | Run in Docker container |
| `--gpu` | — | Enable GPU passthrough |
| `--gpu-type` | — | `cuda` or `rocm` |
| `--image` | — | Container image (default: `ubuntu:24.04`) |
| `--volume` | — | Mount host directory |
| `--workspace` | — | Working directory inside container |

## MiMo Code

MiMo Code is Xiaomi's coding agent. It uses the same profile system.

```bash
# Launch MiMo Code
cf run agent mimo-code
# or
cf r ag mc

# With profile
cf run agent mimo-code --profile bare
# or
cf r ag mc -p bare

# Sandbox mode
cf run agent mimo-code --sandbox
# or
cf r ag mc --sandbox
```

## OpenCode

OpenCode is a terminal-native AI coding agent.

```bash
# Launch OpenCode
cf run agent open-code
# or
cf r ag oc

# With profile
cf run agent open-code --profile bare
# or
cf r ag oc -p bare

# Sandbox mode
cf run agent open-code --sandbox
# or
cf r ag oc --sandbox
```

## Command Reference

### `cf run agent`

```text
usage: codefreedom run agent [-h] [-p PROFILE] [-l] {list,claude-code,mimo-code,open-code} ...

agents:
  {list,claude-code,mimo-code,open-code}
    list                     List available agents
    claude-code (cc)         Claude Code — Anthropic's coding agent
    mimo-code (mc)           MiMoCode — Xiaomi's coding agent with 0-click proxy config
    open-code (oc)           OpenCode — terminal-native AI coding agent with proxy support

options:
  -h, --help            show this help message and exit
  -p, --profile NAME    Load a named profile (default: 'default')
  -l, --list-profiles   List available profiles and exit
```

### Short Aliases

| Full command | Short form |
| ------------ | ---------- |
| `cf run agent claude-code` | `cf r ag cc` |
| `cf run agent mimo-code` | `cf r ag mc` |
| `cf run agent open-code` | `cf r ag oc` |
| `cf run agent claude-code --profile bare` | `cf r ag cc -p bare` |
| `cf run agent claude-code --list-profiles` | `cf r ag cc -l` |
| `cf run agent claude-code --sandbox` | `cf r ag cc --sandbox` |
