---
title: Install
description: Install CodeFreedom in under a minute.
---

# Install

Two prerequisites, one command.

## Prerequisites

| What | Why You Need It | Check |
|------|----------------|-------|
| Python 3.10+ | Runs the CLI | `python3 --version` |
| Docker | Sandbox + proxy | `docker --version` |

**Docker is required for the proxy.** The proxy runs in a Docker container — no host-side `litellm` install needed.

[Install Docker →](https://docs.docker.com/engine/install/)

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

### What It Looks Like

```bash
$ pip install codefreedom
Resolved 3 packages in 320ms
Installed 1 package in 3ms
 + codefreedom==0.1.7
```

## Verify

```bash
codefreedom --version
codefreedom --help
```

You should see the version and a list of commands: `setup`, `run`, `manage`.

## Upgrade

```bash
pip install --upgrade codefreedom
```

## Next Step

[First run →](first-run.md) — initialize config, start the proxy, launch your first session.
