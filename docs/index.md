# Getting Started

Get CodeFreedom up and running in a few minutes.

## How It Works

CodeFreedom is a **unified interface for all code agents** — it does not hack, patch, or modify any code agent. Instead, it provides simple LLM endpoint routing, sandboxing, and profile management through publicly supported interfaces (environment variables, CLI flags, config files, and API endpoints). All configuration lives in `~/.codefreedom`.

> _All product and company names are trademarks of their respective owners.
> See [NOTICE](https://github.com/nilayparikh/codefreedom/blob/main/NOTICE)._

## Prerequisites

| What         | Required For                              | How to Check                                          |
| ------------ | ----------------------------------------- | ----------------------------------------------------- |
| Python 3.10+ | CLI                                       | `python3 --version`                                   |
| Docker       | Sandbox + Docker Compose proxy (optional) | [docker.com](https://docs.docker.com/engine/install/) |
| Node.js      | Local Claude Code                         | `npm install -g @anthropic-ai/claude-code`            |

> **Docker is optional.** The proxy can run natively (`codefreedom proxy --up`). Docker is only required for sandbox mode and Docker Compose proxy.

## Install

```bash
pip install codefreedom
```

Or from source:

```bash
git clone https://github.com/nilayparikh/codefreedom.git
cd codefreedom
pip install -e .
```

Verify it works:

```bash
codefreedom --help
cf --help
```

## Initialize

```bash
# Claude Code profiles + environment
codefreedom claude init

# Proxy configs + environment
codefreedom proxy init
```

This creates `~/.codefreedom/` with profiles, proxy configs, and component-specific `.env` files.

## Start the Proxy

```bash
# Via Docker Compose
codefreedom proxy --up --docker

# Or natively (no Docker needed)
codefreedom proxy --up
```

The proxy starts at `http://localhost:4000`.

## Launch a Code Agent

```bash
# Native mode (default) — runs on your host
codefreedom claude

# Docker sandbox — isolated container with GPU passthrough
codefreedom claude --sandbox

# Pick a built-in profile (or one you created)
codefreedom claude --profile bare
```

All done. You're now running a code agent through the CodeFreedom proxy.

## What's Next?

| Page                            | What You'll Learn                       |
| ------------------------------- | --------------------------------------- |
| [Architecture](architecture.md) | How the pieces fit together             |
| [Proxy](proxy.md)               | Provider setup, database, configuration |
| [Code Agents](claude-code.md)   | Profiles, sandbox mode, local mode      |
