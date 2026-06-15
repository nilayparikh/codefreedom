---
title: CodeFreedom
description: One CLI for every code agent — switch models, isolate environments, stop fighting config.
hide:
  - navigation
  - toc
  - path
---

<div class="cf-hero">
  <h1>CodeFreedom</h1>
  <p class="cf-hero__tagline">
    <strong>One CLI for every code agent.</strong>
    Switch LLM providers, isolate environments, and manage everything from <code>~/.codefreedom</code>.
  </p>
  <div class="cf-hero__install">
    <pre><code>uv tool install codefreedom</code></pre>
  </div>
  <div class="cf-hero__buttons">
    <a href="getting-started/index.md" class="md-button md-button--primary">Get Started</a>
    <a href="https://github.com/nilayparikh/codefreedom" class="md-button">GitHub</a>
  </div>
</div>

## What You Get

- **Switch models instantly** — DeepSeek for drafting, GPT for reasoning, free models for testing. Same command, different profile.
- **Isolated sandboxes** — Every session runs in a fresh Docker container. Clean slate every time.
- **Self-hosted proxy** — One local endpoint (`localhost:4000`) routes to any LLM provider.
- **Browser and API tools** — Headless Chrome, web search, GitHub API — all as Docker containers.

## How It Works

```text
You → cf run agent claude-code → LiteLLM Proxy → Your chosen AI model
```

1. You run `cf run agent claude-code`
2. CodeFreedom sets up environment variables from your profile
3. Claude Code talks to your local proxy at `localhost:4000`
4. The proxy routes the request to whichever AI model you configured

Change the model? Edit one line in your profile. Done.

## Quick Start

```bash
uv tool install codefreedom                              # Install
cf s i -pa costeffective-coding-with-local                # Set up recipe
cf r px start                                            # Start the proxy
cf r ag cc                                               # Launch Claude Code
```

[Get started step by step →](getting-started/index.md)
