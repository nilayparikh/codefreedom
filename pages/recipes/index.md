---
title: Recipes
description: Pre-configured setups for different use cases.
---

Recipes define which providers, secrets, profiles, and proxy configuration are deployed to `~/.codefreedom`. Each recipe extends `_default` (shared tool profiles, base proxy config) and layers its own providers on top.

## Available Recipes

### `costeffective-coding`

Cloud-only inference. Routes through Azure Foundry, OpenCode Zen, OpenRouter, and DeepSeek via the LiteLLM proxy.

**Required secrets:** `PROXY_API_KEY`, `MICROSOFT_FOUNDRY_API_KEY`, `OPENCODE_ZEN_API_KEY`, `OPENROUTER_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`

**Providers:** Azure Foundry (GPT-5.x), OpenCode Zen (MiMo, DeepSeek, Qwen — free + subscription), OpenRouter (DeepSeek, MiMo, Qwen, MiniMax, Kimi, FreeRouter)

[Full documentation →](costeffective-coding.md)

### `costeffective-coding-with-local`

Cloud + local inference. Everything in `costeffective-coding`, plus local Qwen model backends.

**Additional secrets:** `LOCAL_M_API_KEY`, `LOCAL_S_API_KEY`

**Additional providers:** Local Qwen3.6-27B and Qwen3.6-35B-A3B via OpenAI-compatible servers

[Full documentation →](costeffective-coding-with-local.md)

## Apply a Recipe

```bash
cf setup init --plan-and-apply <recipe-name>
```

Short alias:

```bash
cf s i -pa <recipe-name>
```

Example:

```bash
cf s i -pa costeffective-coding
```

## What Happens

1. CodeFreedom clones the recipe from the remote store
2. Generates a plan showing which files will be created, replaced, or left unchanged
3. Applies the plan after confirmation
4. Reports which secrets are set and which are missing

## After Applying

Run the setup script to configure your API keys:

```bash
bash ~/.codefreedom/scripts/<recipe-name>/setup-secrets.sh
```

The script sets `CF_CLI_*` machine environment variables, persists them in your shell profile, and reports which services are configured.

## Recipe Inheritance

Both recipes extend `_default`, which provides:

- Shared tool profiles (Chrome, Web, GitHub, Web Bridge)
- Base proxy Docker Compose configuration
- Base LiteLLM proxy config
- Reasoning efforts plugin mapping

When you switch recipes, shared files are merged (`deepdiff`) so your customizations are preserved. Only recipe-specific files (providers, secrets) are replaced.

## Default Tools

Each recipe configures default tools for each agent. The default tools for OpenCode are:

| Tool | Description |
|------|-------------|
| **github** | GitHub MCP server for repo operations |
| **codebase-memory** | Local code knowledge graph (14 MCP tools) |
| **web** | Camoufox stealth browser for web search/scraping |

To add more tools, edit `~/.codefreedom/config/profiles.yaml`:

```yaml
agents:
  open-code:
    profiles:
      default:
        tools:
          - github
          - codebase-memory
          - web
          - chrome          # Add Chrome for browser automation
          - web-bridge      # Add Web Bridge for search interception
```

See [Tools](https://github.com/nilayparikh/codefreedom#tools) for the full list of available tools and configuration options.
