---
title: Claude Code
description: Launch Claude Code with profile-based model routing, sandbox isolation, and GPU support.
---

# Claude Code

Launch Claude Code through CodeFreedom. Switch models, isolate environments, use GPUs — all with flags.

## Basic Usage

```bash
codefreedom claude              # Local mode (default)
codefreedom claude --sandbox    # Docker sandbox
codefreedom claude --profile bare     # Pick a profile
codefreedom claude --list-profiles    # See what's available
```

Short alias: `cf cc` does the same as `codefreedom claude`.

## Profiles

Profiles control which AI model you use. Think of them as presets.

### Built-in Profiles

| Profile   | Model                 | When to Use                     |
| --------- | --------------------- | ------------------------------- |
| `default` | `${MODEL_NAME}`       | Everyday work                   |
| `bare`    | _(none)_              | Minimal setup, no model aliases |
| `ultra`   | `${MODEL_NAME_ULTRA}` | Architecture, complex reasoning |
| `pro`     | `${MODEL_NAME_PRO}`   | Balanced — implementation work  |
| `air`     | `${MODEL_NAME_AIR}`   | Quick tasks, fast responses     |

### Use a Profile

```bash
codefreedom claude --profile ultra
codefreedom claude --profile air
```

### Create a Custom Profile

Edit `~/.codefreedom/profiles/claude-code.json` and add your profile:

```json
{
  "profiles": {
    "my-work": {
      "description": "My daily driver",
      "env": {
        "CLAUDE_MODEL": "CodeFreedom/Ultra"
      }
    }
  }
}
```

Then use it:

```bash
codefreedom claude --profile my-work
```

## Environment Variable Priority

Claude Code configuration is resolved from multiple sources. Later sources override earlier ones:

| Priority    | Source                               | Example                                     |
| ----------- | ------------------------------------ | ------------------------------------------- |
| 1 (lowest)  | `~/.codefreedom/.env.claude`         | Component config                            |
| 2           | `~/.codefreedom/.env`                | Shared config                               |
| 3           | `{workspace}/.env`                   | Workspace config                            |
| 4           | `~/.codefreedom/.env.claude.secrets` | Component secrets                           |
| 5           | `~/.codefreedom/.env.secrets`        | Shared secrets                              |
| 6           | `{workspace}/.env.secrets`           | Workspace secrets                           |
| 7           | `~/.codefreedom/.env.user`           | User overrides (never touched by recipes)   |
| 8           | Machine environment (`os.environ`)   | Exported shell vars                         |
| 9 (highest) | `CF_CLI_*` overrides                 | `export CF_CLI_ANTHROPIC_AUTH_TOKEN=sk-...` |

**`CF_CLI_*` overrides** let you force-set any value from your shell without editing `.env` files. The prefix is stripped and the value is applied as the final override — above files, above `os.environ`, above everything:

```bash
# In ~/.bashrc — always wins
export CF_CLI_LITELLM_MASTER_KEY=sk-d3k5Zz9gWx...
export CF_CLI_ANTHROPIC_AUTH_TOKEN=sk-...
```

**Inheritance:** Custom profiles automatically inherit from `default`. You only set what differs.

## Sandbox Mode

Run Claude Code in an isolated Docker container. Fresh environment every time, cleaned up when you exit.

```bash
codefreedom claude --sandbox           # Default (Ubuntu)
codefreedom claude --sandbox --cuda    # NVIDIA GPU
codefreedom claude --sandbox --rocm    # AMD GPU
codefreedom claude --sandbox --run-as-me   # Run as your user
```

### Sandbox Images

| Image  | Use Case                  | Tag           |
| ------ | ------------------------- | ------------- |
| Ubuntu | CPU-only, general purpose | `latest`      |
| CUDA   | NVIDIA GPU (AI workloads) | `cuda-latest` |
| ROCm   | AMD GPU (AI workloads)    | `rocm-latest` |

All images include Claude Code, Node.js, Python, Git, and essential dev tools.

### How Sandboxes Work

- Each session gets a random container name (`codefreedom-XXXX`)
- Container is destroyed when you exit (`Ctrl+C` or `/exit`)
- Your profile's state is isolated at `~/.codefreedom/sandbox/<profile>/.claude/`
- No state leaks between sessions

### GPU Requirements

| Image  | Requirement                                                                                                                          |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| CUDA   | NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) |
| ROCm   | AMD GPU + ROCm support                                                                                                               |
| Ubuntu | No GPU needed                                                                                                                        |

No GPU? Use Ubuntu:

```bash
export CLAUDE_CODE_IMAGE_TAG=latest
codefreedom claude --sandbox
```

## Local Mode

Run Claude Code directly on your machine. No Docker, no isolation.

```bash
codefreedom claude                  # Local, through proxy
codefreedom claude --native-models  # Local, bypass proxy (use Anthropic directly)
```

### Local vs Sandbox

| Aspect    | Sandbox                  | Local              |
| --------- | ------------------------ | ------------------ |
| Isolation | Full container           | Host environment   |
| GPU       | Automatic (`--gpus all`) | Manual setup       |
| State     | Per-profile, isolated    | Shared `~/.claude` |
| Cleanup   | Auto on exit             | N/A                |

## Bypass the Proxy

Use `--native-models` to skip the proxy and use Anthropic directly:

```bash
codefreedom claude --native-models
codefreedom claude --sandbox --native-models
```

This uses your Anthropic credentials directly — no proxy routing.

## Code Intelligence (LSP)

Sandbox images include language server binaries. Install plugins inside a session:

```bash
/plugin install typescript-lsp@claude-plugins-official
/plugin install pyright-lsp@claude-plugins-official
/plugin install rust-analyzer-lsp@claude-plugins-official
/plugin install clangd-lsp@claude-plugins-official
```

Then `/reload-plugins` to activate.

## Common Commands

```bash
codefreedom claude --list-profiles    # List profiles
codefreedom claude --status           # Show container status (sandbox)
codefreedom claude --stop             # Stop all sandbox containers
```
