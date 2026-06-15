# docker/open-code

Docker image for running OpenCode in isolated sandbox containers.

## Image Variants

| Variant | Dockerfile | Base | Arch |
| --- | --- | --- | --- |
| **Ubuntu** | `Dockerfile.Ubuntu` | `ubuntu:24.04` | amd64, arm64 |

## Build

```bash
docker build --build-arg IMAGE_VERSION=1.0.0 \
  -t codefreedom:open-code-v1.0.0 \
  -f docker/open-code/Dockerfile.Ubuntu docker/open-code/
```

## Usage with CodeFreedom

```bash
codefreedom run agent open-code                # local mode
codefreedom run agent open-code --sandbox      # sandboxed container
```

## Container Design

- Ephemeral containers with random 4-hex names (`codefreedom-XXXX`), auto-removed on exit
- Container runs `sleep infinity`; OpenCode is `docker exec`'d into it
- Volume mounts: workspace (rw), `~/.gitconfig` (ro), `~/.ssh` (ro)
- Non-root user `codefreedom` (uid 1000) with passwordless sudo

## Registry

Published images:

- `docker.io/nilayparikh/codefreedom:open-code-latest`
- `ghcr.io/nilayparikh/codefreedom:open-code-latest`
