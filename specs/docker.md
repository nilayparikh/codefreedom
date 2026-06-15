# Docker Images & Naming

Docker image families, naming conventions, and publishing.

## Naming Convention

Docker tags **must be lowercase**. Examples:

| Correct | Incorrect |
| --- | --- |
| `codefreedom:chrome` | `codefreedom:Chrome` |
| `codefreedom:cuda-latest` | `codefreedom:CUDA-latest` |

## Image Families

| Image | Dockerfile | Use Case |
| --- | --- | --- |
| **CUDA** | `docker/claude-code/Dockerfile.CUDA` | NVIDIA GPU workloads |
| **ROCm** | `docker/claude-code/Dockerfile.ROCm` | AMD GPU workloads |
| **Ubuntu** | `docker/claude-code/Dockerfile.Ubuntu` | CPU-only / general-purpose |
| **Chrome** | `docker/chrome/Dockerfile.Chrome` | Headless Chromium (CDP port 9222) |
| **Web** | `docker/web/Dockerfile.Web` | Camoufox MCP (stealth web search) |
| **GitHub MCP** | `docker/github/Dockerfile.Github` | GitHub API tools (port 8082) |
| **LiteLLM** | `docker/litellm/Dockerfile.LiteLLM` | LLM proxy with embedded PostgreSQL |
| **Web Bridge** | `docker/web-bridge/Dockerfile.Bridge` | SearXNG → Camoufox bridge |

## Docker Compose

The proxy always runs via `docker compose` against `~/.codefreedom/proxy/docker-compose.yaml`. No host-side `litellm` install is required.

## Patches

Patches in `docker/litellm/patches/` are applied during image build. If you change LiteLLM and a patch can no longer find its target, the build fails loudly — do not silently fall back.
