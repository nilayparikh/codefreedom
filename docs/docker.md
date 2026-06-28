# Docker Images & Naming

Docker image families, naming conventions, and publishing.

## Naming Convention

Docker tags **must be lowercase**. Examples:

| Correct | Incorrect |
|---|---|
| `codefreedom:chrome` | `codefreedom:Chrome` |
| `codefreedom:cuda-latest` | `codefreedom:CUDA-latest` |

## Image Families

| Image | Dockerfile | Use Case |
|---|---|---|
| **Chrome** | `docker/chrome/Dockerfile.Chrome` | Headless Chromium (CDP port 9222) |
| **Web** | `docker/web/Dockerfile.Web` | Camoufox MCP (stealth web search) |
| **GitHub MCP** | `docker/github/Dockerfile.Github` | GitHub API tools (port 8082) |
| **LiteLLM** | `docker/litellm/Dockerfile.LitellmFinal` | LLM proxy with embedded PostgreSQL |
| **LiteLLM Base** | `docker/litellm/Dockerfile.LitellmBase` | LiteLLM base image (monthly rebuild) |
| **PG Base** | `docker/litellm/Dockerfile.PgBase` | PostgreSQL base image (quarterly rebuild) |
| **Web Bridge** | `docker/web-bridge/Dockerfile.Bridge` | SearXNG -> Camoufox bridge |

## Docker Workflows

All Docker workflows are manual trigger only (`workflow_dispatch`).

| Workflow | Image | Inputs |
|---|---|---|
| `docker-chrome.yml` | Chrome browser | `tag` (required), `latest` (default: true) |
| `docker-litellm.yml` | LiteLLM proxy | `tag` (required), `latest` (default: true), `litellm_base_tag` (optional) |
| `docker-web.yml` | Camoufox MCP | `tag` (required), `latest` (default: true) |
| `docker-web-bridge.yml` | Web Bridge | `tag` (required), `latest` (default: true) |
| `docker-github.yml` | GitHub MCP | `tag` (required), `latest` (default: true) |
| `docker-litellm-base.yml` | LiteLLM base | `litellm_tag` (required), `pg_base_tag` (required) |
| `docker-litellm-pg-base.yml` | PostgreSQL base | `pg_version` (required), `pg_tag` (required) |

## Docker Compose

The proxy always runs via `docker compose` against `~/.codefreedom/config/proxy/docker-compose.yaml`. No host-side `litellm` install is required.

## Bind Address

All Docker services (proxy and tools) bind to `0.0.0.0` by default, making them accessible from any network interface. This allows remote clients to connect using the host's IP address.

To restrict to loopback-only (local access only), set the bind address:

```bash
# Via CLI
cf setup config bind --address 127.0.0.1

# Or via override.yaml
common:
  bind_address: "127.0.0.1"

# Or via env var
export CF_CLI_BIND_ADDRESS=127.0.0.1
```

**Remote access:** When services bind to `0.0.0.0`, remote clients can connect using the host's IP. Configure remote access per-component:

```bash
# Remote proxy
cf setup config proxy --remote-url http://192.168.1.5:4000

# Remote tool
cf setup config tools chrome --remote-url http://192.168.1.5:9223
```

## Patches

Patches in `docker/litellm/patches/` are applied during image build. If you change LiteLLM and a patch can no longer find its target, the build fails loudly -- do not silently fall back.

## LiteLLM Checkpoint Builds

The LiteLLM image uses a 3-stage checkpoint build system:

1. **PG Base** (`litellm-pg-base`) -- PostgreSQL compiled from source (quarterly rebuild)
2. **LiteLLM Base** (`litellm-base`) -- LiteLLM + dependencies + Prisma (monthly rebuild)
3. **LiteLLM Final** (`litellm`) -- Patches + plugins + entrypoint (every PR, ~1-2 min)

This reduces CI build time from 30-40 minutes to 1-2 minutes for routine changes.
