---
title: Get Started
description: Install CodeFreedom and launch your first agent in five minutes.
---

## Video Walkthrough

<div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%;">
  <iframe src="https://www.youtube.com/embed/6tgVffZwSrU" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen loading="lazy"></iframe>
</div>

## Prerequisites

- **Python 3.10+** — for the CLI
- **Docker** — for proxy and tool containers
- **uv** — Python package manager

Install uv if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Install CodeFreedom

```bash
uv tool install codefreedom
```

## Install Code Agents

CodeFreedom does **not** install, modify, or patch code agents. It only calls them with the correct configuration and environment variables. Each agent must be installed through its official installation method:

- **Claude Code** — install via `npm install -g @anthropic/claude-code` or follow [Anthropic's docs](https://docs.anthropic.com/en/docs/agents/claude-code/overview)
- **MiMo Code** — install via `npm install -g @mimo/mimo-code` or follow the official MiMo Code documentation
- **OpenCode** — install via the official OpenCode distribution

CodeFreedom sets `ANTHROPIC_BASE_URL`, `CLAUDE_MODEL`, and other environment variables so agents route through your local proxy. No agent code is touched.

## Set Up

Apply a recipe to generate your `~/.codefreedom` configuration:

```bash
cf setup init --plan-and-apply costeffective-coding
```

Or with short alias:

```bash
cf s i -pa costeffective-coding
```

## Set Up Secrets

After setup, run the assisted script to configure your API keys:

```bash
bash ~/.codefreedom/scripts/costeffective-coding/setup-secrets.sh
```

This adds `CF_CLI_*` environment variables to your shell profile:

```text
# >>> codefreedom:costeffective-coding secrets >>>
export CF_CLI_LITELLM_MASTER_KEY="sk-..."
export CF_CLI_MICROSOFT_FOUNDRY_API_BASE="https://...services.ai.azure.com/openai/v1"
export CF_CLI_MICROSOFT_FOUNDRY_API_KEY="..."
export CF_CLI_OPENCODE_ZEN_API_KEY="..."
export CF_CLI_OPENROUTER_API_KEY="..."
export CF_CLI_GITHUB_PERSONAL_ACCESS_TOKEN="github_pat_..."
# <<< codefreedom:costeffective-coding secrets <<<
```

## Start the Proxy

```bash
cf run proxy start
```

Or with short alias:

```bash
cf r px start
```

<figure markdown="span">
  ![Proxy started](../assets/proxy-started.png){ width="700" }
  <figcaption>Proxy running at localhost:4000</figcaption>
</figure>

## Launch an Agent

```bash
cf run agent claude-code
```

Or with short alias:

```bash
cf r ag cc
```

<figure markdown="span">
  ![Claude Code running](../assets/claude-code-running.png){ width="700" }
  <figcaption>Claude Code connected via proxy</figcaption>
</figure>

## Available Agents

| Agent | Command | Alias |
| --- | --- | --- |
| Claude Code | `cf r ag cc` | `cc` |
| MiMo Code | `cf r ag mc` | `mc` |
| OpenCode | `cf r ag oc` | `oc` |
| Pi Code | `cf r ag pc` | `pc` |
| Codex | `cf r ag cx` | `cx` |

## Quick Reference

| Command | Short | Description |
| --- | --- | --- |
| `cf setup init` | `cf s i` | Set up config |
| `cf run proxy start` | `cf r px start` | Start the proxy |
| `cf run agent claude-code` | `cf r ag cc` | Launch Claude Code |
| `cf manage doctor` | `cf m dr` | Check system health |
