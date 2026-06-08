---
title: CodeFreedom
description: One CLI for every code agent — switch models, isolate environments, stop fighting config.
hide:
  - navigation
  - toc
---

<div class="cf-hero">
  <h1>CodeFreedom</h1>
  <p class="cf-hero__tagline">
    <strong>One CLI for every code agent.</strong>
    Switch LLM providers, isolate environments, and manage everything from <code>~/.codefreedom</code>.
  </p>
  <div class="cf-hero__install">
    <pre><code>pip install codefreedom</code></pre>
  </div>
  <div class="cf-hero__buttons">
    <a href="getting-started/install.md" class="md-button md-button--primary">Get Started</a>
    <a href="https://github.com/nilayparikh/codefreedom" class="md-button">GitHub</a>
  </div>
</div>

## What Problem Does This Solve

You have code agents (Claude Code, Cursor, etc.). You want to switch between AI models (DeepSeek, GPT, Claude) without reconfiguring everything. You want isolated environments. You want one place for all your settings.

CodeFreedom gives you that.

## What You Get

<div class="grid cards" markdown>

- :material-swap-horizontal:{ .lg .middle } **Switch models instantly**

  ***

  DeepSeek for drafting, GPT for reasoning, free models for testing. Same command, different profile. No code changes.

  [:octicons-arrow-right-24: Claude Code](features/claude-code.md)

- :material-docker:{ .lg .middle } **Isolated sandboxes**

  ***

  Every session runs in a fresh Docker container. CUDA, ROCm, or plain Ubuntu. Clean slate every time.

  [:octicons-arrow-right-24: Sandbox](features/claude-code.md#sandbox-mode)

- :material-graph-outline:{ .lg .middle } **Self-hosted proxy**

  ***

  One local endpoint (`localhost:4000`) routes to any LLM provider. Add API keys, switch backends, track spend.

  [:octicons-arrow-right-24: Proxy](features/proxy.md)

- :material-toolbox-outline:{ .lg .middle } **Browser and API tools**

  ***

  Headless Chrome, web search, GitHub API — all as Docker containers your code agent can use.

  [:octicons-arrow-right-24: Tools](features/tools.md)

</div>

## How It Works

```
You → codefreedom claude → LiteLLM Proxy → Your chosen AI model
```

1. You run `codefreedom claude`
2. CodeFreedom sets up environment variables from your profile
3. Claude Code talks to your local proxy at `localhost:4000`
4. The proxy routes the request to whichever AI model you configured

Change the model? Edit one line in your profile. Done.

## Quick Start

Four commands, five minutes:

```bash
pip install codefreedom          # Install
codefreedom --init               # Set up config
codefreedom proxy start          # Start the proxy
codefreedom claude               # Launch Claude Code
```

[Get started step by step →](getting-started/install.md)
