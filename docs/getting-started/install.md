---
title: Install
description: Install the CodeFreedom CLI and its prerequisites.
---

# Install

Two prerequisites, one command. The whole install takes about a minute.

## Prerequisites

| What         | Required For                                 | How to Check                                          |
| ------------ | -------------------------------------------- | ----------------------------------------------------- |
| Python 3.10+ | CLI                                          | `python3 --version`                                   |
| Docker       | Sandbox + proxy (hard prerequisite for both) | [docker.com](https://docs.docker.com/engine/install/) |

> **Docker is required for the proxy.** The proxy always runs via `docker compose` against the self-hosted `codefreedom:litellm-latest` image — no host-side `litellm` install is needed.

## Install the CLI

=== "Linux / macOS"

    ```bash
    pip install codefreedom
    ```

=== "Windows"

    ```powershell
    py -3 -m pip install codefreedom
    ```

=== "From source"

    ```bash
    git clone https://github.com/nilayparikh/codefreedom.git
    cd codefreedom
    pip install -e ".[all]"
    ```

## Verify

```bash
codefreedom --version
codefreedom --help
```

You should see the version and the top-level command list (`claude`, `proxy`, `tools`, `admin`, `vscode`).

## Next step

[First run →](first-run.md)
