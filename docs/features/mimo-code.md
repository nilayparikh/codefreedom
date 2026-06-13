# MiMoCode

MiMoCode is Xiaomi's coding agent, supported as a first-class citizen in CodeFreedom.

## Quick Start

```bash
# Launch MiMoCode natively
cf mimo

# Launch in sandbox
cf mimo --sandbox

# Short alias
cf mc
```

## Proxy Integration

MiMoCode gets zero-click proxy configuration:

1. CodeFreedom detects the running LiteLLM proxy
2. Fetches the model list from `/v1/models`
3. Generates `~/.codefreedom/mimo-code/mimocode.json` with all proxy models
4. Sets `MIMOCODE_CONFIG` env var to point at the generated config
5. MiMoCode loads all proxy models as `codefreedom/<model-id>`

No manual configuration needed — just start the proxy and launch.

## Sandbox Mode

```bash
cf mimo --sandbox
```

Runs MiMoCode inside an ephemeral Docker container with:

- GPU passthrough (NVIDIA/AMD)
- Isolated `.claude` directory
- Tool containers auto-acquired
- Clean session on every run

## Profile Behavior

Profiles are loaded from `~/.codefreedom/profiles/mimo-code.yaml`.

```bash
# List available profiles
cf mimo --list-profiles

# Use a specific profile
cf mimo --profile production
```

## Shared Infrastructure

MiMoCode uses the same CodeFreedom layers as Claude Code:

- **Config:** Same `~/.codefreedom` directory structure
- **Proxy:** Same LiteLLM proxy for model routing
- **Tools:** Same tool registry (Chrome, Web, GitHub)
- **Sandbox:** Same Docker sandbox launcher
- **Profiles:** Same profile inheritance model

## Differences from Claude Code

| Aspect | Claude Code | MiMoCode |
|--------|------------|----------|
| Config file | `.claude.json` | `mimocode.json` |
| Profiles path | `profiles/claude-code.yaml` | `profiles/mimo-code.yaml` |
| Default image | `codefreedom:latest` | `codefreedom:mimo-code` |
| Binary | `claude` | `mimo` |
