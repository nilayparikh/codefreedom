# docker/mimo-code

Docker image for running MiMoCode in isolated sandbox containers.

## Image Variants

| Variant | Dockerfile | Base | Arch |
| --- | --- | --- | --- |
| **Ubuntu** | `Dockerfile.Ubuntu` | `ubuntu:24.04` | amd64, arm64 |

## Build

```bash
docker build --build-arg IMAGE_VERSION=1.0.0 \
  -t codefreedom:mimo-code-v1.0.0 \
  -f docker/mimo-code/Dockerfile.Ubuntu docker/mimo-code/
```

## Usage with CodeFreedom

```bash
codefreedom run agent mimo-code                # local mode
codefreedom run agent mimo-code --sandbox      # sandboxed container
```

## Container Design

- Ephemeral containers with random 4-hex names (`codefreedom-XXXX`), auto-removed on exit
- Container runs `sleep infinity`; MiMoCode is `docker exec`'d into it
- Volume mounts: workspace (rw), `~/.gitconfig` (ro), `~/.ssh` (ro)
- Non-root user `codefreedom` (uid 1000) with passwordless sudo

## Registry

Published images:

- `docker.io/nilayparikh/codefreedom:mimo-code-latest`
- `ghcr.io/nilayparikh/codefreedom:mimo-code-latest`
