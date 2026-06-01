# Getting Started

This guide walks you through installing and configuring CodeFreedom.

## Prerequisites

| Dependency               | Required For                | Installation                                               |
| ------------------------ | --------------------------- | ---------------------------------------------------------- |
| Python 3.10+             | CLI                         | `python3 --version`                                        |
| Docker                   | Docker mode + LiteLLM proxy | [docs.docker.com](https://docs.docker.com/engine/install/) |
| NVIDIA Container Toolkit | GPU passthrough             | `nvidia-ctk runtime configure --runtime=docker`            |
| Node.js + `claude` CLI   | `--local` mode              | `npm install -g @anthropic-ai/claude-code`                 |

## Installation

### From Source (Recommended)

```bash
git clone https://github.com/nilayparikh/codefreedom.git
cd codefreedom
pip install -e .
```

Verify the installation:

```bash
codefreedom --help
cf --help
```

## I want to use...

| Your use case                                 | Jump to                                                                                          |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Cloud APIs only** (DeepSeek, Azure, etc.)   | [Configuration → Adding a cloud provider](configuration.md#adding-a-cloud-provider)              |
| **Self-hosted OpenAI-compatible endpoint**    | [Configuration → OpenAI-compatible](configuration.md#adding-an-openai-compatible-endpoint)       |
| **Self-hosted Anthropic-compatible endpoint** | [Configuration → Anthropic-compatible](configuration.md#adding-an-anthropic-compatible-endpoint) |
| **Anthropic API directly** (no proxy)         | Use `codefreedom claude --profile bare`                                                          |

### Configuration

```bash
# Copy the example config and environment files
cp -r litellm.examples/config litellm/
cp litellm.examples/.env.example .env
cp litellm.examples/.env.secrets.example .env.secrets

# Edit .env.secrets with your API keys (NEVER commit this file)
# At minimum, set LITELLM_MASTER_KEY (proxy auth — required)
```

> **What's happening:** `litellm.examples/` has fully documented templates with
> every option explained inline. You copy them into `litellm/` (runtime — gitignored)
> and `.env` / `.env.secrets` at the project root.

For cloud providers, add your API keys to `.env.secrets`:

```bash
# .env.secrets (NEVER commit this file)
LITELLM_MASTER_KEY=sk-your-proxy-key   # Required — proxy auth token
DEEPSEEK_API_KEY=sk-your-key           # Optional — leave empty to disable
MICROSOFT_FOUNDRY_API_KEY=your-key     # Optional
NVIDIA_API_KEY=nvapi-your-key          # Optional
OPENCODE_ZEN_API_KEY=your-key          # Optional
```

### Start the Proxy

```bash
# Using codefreedom CLI (recommended)
codefreedom proxy --up

# Or using Docker Compose directly
docker compose --profile all up -d
```

Verify it's running:

```bash
cf proxy --status
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer $(grep LITELLM_MASTER_KEY .env.secrets | cut -d= -f2)"
```

### Database (Optional)

The proxy runs **stateless by default** — no database, no Prisma, no persistence.
Model routing works out of the box. The LiteLLM Admin UI, spend tracking, and
key management require a PostgreSQL database.

To add PostgreSQL later:

```bash
# .env
DATABASE_URL=postgresql://litellm_interface:YOUR_PASSWORD@postgres:5432/litellm_interface

# Then update litellm/config/config.yaml:
#   - Uncomment: database_url: os.environ/DATABASE_URL
#   - Change store_model_in_db: false → true
#   - Change store_prompts_in_spend_logs: false → true
```

See [LiteLLM Proxy → Database](litellm.md#database-backends) for details.

````

If using `.init`'s PostgreSQL, ensure both projects share the same Docker network:

```bash
# The .init stack creates an 'init_default' network.
# To connect codefreedom to it, add this to litellm/docker-compose.litellm.yml:
networks:
  default:
    external: true
    name: init_default
````

## Starting the Proxy

```bash
# Via docker compose
docker compose up -d

# Or via the CLI
codefreedom proxy --up

# Check status
codefreedom proxy --status
```

The LiteLLM proxy is now running at `http://localhost:4000`.

## Launching Claude Code

```bash
# Basic invocation (Docker mode, Flash model)
codefreedom claude

# Or with the short alias
cf cc

# Pick a model profile
cf cc --profile pro      # Implementation work
cf cc --profile ultra    # Architecture/planning
cf cc --profile bare     # Native Anthropic auth

# Run without Docker (requires Node.js + claude CLI)
cf cc --local

# Pass arguments to Claude
cf cc -p "Write a function that..."
cf cc --resume "<session-id>"

# Manage the persistent container
cf cc --stop             # Stop and remove container
cf cc --status           # Show container status
cf cc --list-profiles    # List available profiles
```

## CLI Reference

All commands have short aliases. Use `codefreedom` or `cf` interchangeably.

| Command                  | Alias              | Action                       | Equivalent Docker Compose            |
| ------------------------ | ------------------ | ---------------------------- | ------------------------------------ |
| `cf proxy --up`          | `cf px --up`       | Start LiteLLM proxy (Docker) | `docker compose --profile all up -d` |
| `cf proxy --down`        | `cf px --down`     | Stop LiteLLM proxy           | `docker compose --profile all down`  |
| `cf proxy --status`      | `cf px --status`   | Show proxy status            | `docker compose ps`                  |
| `cf proxy --validate`    | `cf px --validate` | Validate LiteLLM config      | —                                    |
| `cf proxy --up --native` | —                  | Run litellm without Docker   | —                                    |
| `cf claude`              | `cf cc`            | Launch Claude Code (Docker)  | —                                    |
| `cf cc --local`          | —                  | Run Claude Code natively     | —                                    |
| `cf cc --profile NAME`   | —                  | Use named profile            | —                                    |
| `cf cc --stop`           | —                  | Stop Claude container        | —                                    |

## Profiles

Profiles are defined in `profiles/claude-code-profiles.json`. The default profile routes through your local LiteLLM proxy at `http://localhost:4000`.

To create a custom profile, add an entry:

```json
{
  "profiles": {
    "my-remote": {
      "description": "Routes through a remote LiteLLM proxy",
      "env": {
        "ANTHROPIC_BASE_URL": "https://my-proxy.example.com",
        "ANTHROPIC_AUTH_TOKEN": "sk-remote-key",
        "CLAUDE_MODEL": "CodeFreedom/Ultra"
      }
    }
  }
}
```

Custom profiles automatically inherit all settings from `default` — you only need to specify what's different.

## Provider Setup

> **Not sure which providers you need?** See the [Configuration Guide](configuration.md)
> for step-by-step walkthroughs — including how to add OpenAI-compatible and
> Anthropic-compatible endpoints, and how to **disable providers you don't need**.

### DeepSeek (Default Cloud Provider)

Set your API key in `.env.secrets`:

```bash
DEEPSEEK_API_KEY=sk-your-deepseek-key
```

### Microsoft Foundry (Azure)

```bash
MICROSOFT_FOUNDRY_API_KEY=your-azure-key
```

### NVIDIA AI Endpoints

```bash
NVIDIA_API_KEY=nvapi-your-key
```

### OpenCode Zen (Free Tier)

```bash
OPENCODE_ZEN_API_KEY=your-zen-key
```

### Local (Self-Hosted)

If you have an OpenAI-compatible backend running locally, see
[Adding an OpenAI-compatible endpoint](configuration.md#adding-an-openai-compatible-endpoint)
in the Configuration Guide.

## Next Steps

- **[Configuration Guide](configuration.md)** — add OpenAI/Anthropic-compatible endpoints, cloud providers, model aliases
- [LiteLLM Proxy Configuration](litellm.md) — providers, model aliases, database setup
- [Claude Code Launcher](claude-code.md) — profiles, Docker lifecycle, advanced usage
