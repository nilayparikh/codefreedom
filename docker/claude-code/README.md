# docker/claude-code

Docker images for running Claude Code in isolated sandbox containers with CPU, NVIDIA GPU, or AMD GPU support.

## Image Variants

Three Dockerfiles share the same toolchain; they differ only in their base image and AI framework:

| Variant | Dockerfile | Base | GPU | Arch |
| --- | --- | --- | --- | --- |
| **Ubuntu** | `Dockerfile.Ubuntu` | `ubuntu:26.04` | None (CPU-only) | amd64, arm64 |
| **CUDA** | `Dockerfile.CUDA` | `nvcr.io/nvidia/pytorch:26.04-py3` | NVIDIA (CUDA 13.2.1, PyTorch 2.12) | amd64, arm64 |
| **ROCm** | `Dockerfile.ROCm` | `rocm/pytorch:rocm7.2.4_ubuntu24.04_py3.12_pytorch_release_2.10.0` | AMD (ROCm 7.2.4, PyTorch 2.10) | amd64 only |

## Shared Toolchain

All variants include:

- **Claude Code** (via npm)
- **Node.js LTS** (v20)
- **Python 3** with venv and pip
- **Git**, **GitHub CLI** (`gh`)
- **Dev tools**: shellcheck, fd-find, tree, ripgrep, jq, yq, zoxide, sd, ast-grep, difftastic, scc, watchexec
- **Language servers**: typescript-language-server, pyright, rust-analyzer, clangd
- **Trivy** security scanner with MCP plugin
- **Productivity**: bubblewrap (sandboxing), socat, openssh-client

## Build

```bash
# Ubuntu (CPU-only)
docker build --build-arg IMAGE_VERSION=0.1.0 \
  -t codefreedom:ubuntu-v0.1.0 \
  -f docker/claude-code/Dockerfile.Ubuntu docker/claude-code/

# CUDA (NVIDIA GPU)
docker build --build-arg IMAGE_VERSION=0.1.0 \
  -t codefreedom:cuda-v0.1.0 \
  -f docker/claude-code/Dockerfile.CUDA docker/claude-code/

# ROCm (AMD GPU)
docker build --build-arg IMAGE_VERSION=0.1.0 \
  -t codefreedom:rocm-v0.1.0 \
  -f docker/claude-code/Dockerfile.ROCm docker/claude-code/
```

## Usage with CodeFreedom

```bash
# CPU-only sandbox
codefreedom claude --sandbox

# NVIDIA GPU sandbox
codefreedom claude --sandbox --cuda

# AMD GPU sandbox
codefreedom claude --sandbox --rocm
```

## Container Design

- Ephemeral containers with random 4-hex names (`codefreedom-XXXX`), auto-removed on exit via `--rm`
- Container runs `sleep infinity`; Claude Code is `docker exec`'d into it
- Volume mounts: workspace (rw), `~/.gitconfig` (ro), `~/.ssh` (ro), isolated `~/.codefreedom/sandbox/<profile>/.claude`
- Non-root user `codefreedom` (uid 1000) with passwordless sudo
- `--run-as-me` option matches host uid/gid for seamless file permissions

## Environment Variables

Set automatically in the container:

| Variable | Value | Purpose |
| --- | --- | --- |
| `CLAUDE_CODE_ATTRIBUTION_HEADER` | `0` | Skip attribution header |
| `IS_SANDBOX` | `1` | Signal to tooling this is a sandbox |
| `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` | `1` | Skip IDE auto-install |
| `CLAUDE_CODE_AUTO_CONNECT_IDE` | `false` | Disable IDE auto-connect |
| `CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL` | `1` | Skip marketplace auto-install |
| `DISABLE_INSTALLATION_CHECKS` | `1` | Skip installation checks |

## Registry

Published images are available on:
- `docker.io/nilayparikh/codefreedom` (tags: `cuda-v0.1.0`, `rocm-v0.1.0`, `ubuntu-v0.1.0`)
- `ghcr.io/nilayparikh/codefreedom` (mirror)
