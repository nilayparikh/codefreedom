# Code Agents

Launch code agents with profile-based model routing through your LLM proxy.

> **No hacks.** CodeFreedom orchestrates code agents through their publicly
> documented interfaces -- environment variables, CLI flags, and API endpoints.
> It does not patch, reverse-engineer, or tamper with any code agent.

## Quick Reference

```bash
codefreedom claude              # Native mode (default)
codefreedom claude --sandbox    # Docker sandbox
codefreedom claude --profile bare     # Pick a built-in profile
codefreedom claude --list-profiles    # List available profiles
codefreedom claude --stop       # Stop sandbox containers
codefreedom claude --status     # Show container status
codefreedom claude --run-as-me   # Run sandbox as host user (with --sandbox)
codefreedom claude --cuda        # Use CUDA GPU image (with --sandbox)
codefreedom claude --rocm        # Use ROCm GPU image (with --sandbox)
```

Short aliases: `cf cc` is equivalent to `codefreedom claude`.

## Execution Modes

| Mode | Command | Use When... |
|------|---------|-------------|
| [Local (Native)](claude-code/local.md) | `codefreedom claude` | Running on your host, no isolation needed |
| [Sandbox](claude-code/sandbox.md) | `codefreedom claude --sandbox` | Isolated Docker container with GPU passthrough |

Both modes support `--profile` for model switching and `--native-models` to bypass the proxy and use native auth.

## Sandbox Images

Three pre-configured images (CUDA, ROCm, Ubuntu) on `docker.io/nilayparikh/codefreedom`. (Also available on `ghcr.io/nilayparikh/codefreedom` as a mirror.)
See [Sandbox Mode -> Available Images](claude-code/sandbox.md#available-images) for the full tag reference and Dockerfile examples.

## Profile System

Profiles control which model a code agent uses by setting environment variables. All profiles live in `~/.codefreedom/profiles/claude-code.json`, validated against `~/.codefreedom/profiles/claude-code.schema.json`.

### Built-in Profiles

| Profile | Model | Description |
|---------|-------|-------------|
| `default` | `${MODEL_NAME}` | Base profile -- routes through proxy, sets all model defaults |
| `bare` | _(none)_ | Minimal -- routes through proxy, no model aliases or preferences |
| `ultra` | `${MODEL_NAME_ULTRA}` | Inherits from `default` -- best reasoning for architecture/planning |
| `pro` | `${MODEL_NAME_PRO}` | Inherits from `default` -- balanced for bounded implementation |
| `air` | `${MODEL_NAME_AIR}` | Inherits from `default` -- lightweight for mechanical tasks |

The model aliases (`${MODEL_NAME}`, `${MODEL_NAME_PRO}`, `${MODEL_NAME_ULTRA}`, `${MODEL_NAME_AIR}`) are defined in the [proxy configuration](proxy/config.md#model-aliases), not in profiles.

---

For the complete profile reference -- inheritance mechanics, variable interpolation, schema validation, tool declarations, sandbox images, and tool profiles -- see [Profiles](claude-code/profiles.md).

For sandbox isolation details -- container lifecycle, file system isolation, network isolation, GPU passthrough, and security trade-offs -- see [Sandbox Isolation](claude-code/sandbox-isolation.md).

See [Environment Configuration](environment.md) for the full env chain and variable interpolation details.
