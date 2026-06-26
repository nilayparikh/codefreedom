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

## Patches

Patches in `docker/litellm/patches/` are applied during image build. If you change LiteLLM and a patch can no longer find its target, the build fails loudly -- do not silently fall back.

## LiteLLM Checkpoint Builds

The LiteLLM image uses a 3-stage checkpoint build system:

1. **PG Base** (`litellm-pg-base`) -- PostgreSQL compiled from source (quarterly rebuild)
2. **LiteLLM Base** (`litellm-base`) -- LiteLLM + dependencies + Prisma (monthly rebuild)
3. **LiteLLM Final** (`litellm`) -- Patches + plugins + entrypoint (every PR, ~1-2 min)

This reduces CI build time from 30-40 minutes to 1-2 minutes for routine changes.
