---
title: Help
description: Troubleshooting and frequently asked questions.
---

# Help

Common problems and how to fix them.

## Proxy Won't Start

### "Could not find docker-compose.yaml"

```
[ERROR] Could not find ~/.codefreedom/proxy/docker-compose.yaml
```

**Fix:** Initialize the proxy first.

```bash
codefreedom proxy init
```

### Port Already in Use

**Fix:** Use a different port.

```bash
codefreedom proxy start --port 4001
```

## Profile Issues

### "Profile not found"

```bash
codefreedom claude --list-profiles    # See what exists
```

Then either use an existing profile or add yours to `~/.codefreedom/profiles/claude-code.json`.

### Profile Not Applying Expected Model

Checklist:

1. `codefreedom claude --list-profiles` — verify profile exists
2. `codefreedom proxy validate` — check model aliases
3. `codefreedom proxy status` — confirm proxy is running

## Sandbox Issues

### "Failed to start container"

Checklist:

1. Is Docker running? `docker info`
2. Is the image pulled? `docker pull docker.io/nilayparikh/codefreedom:latest`

### GPU Errors

Sandbox mode uses `--gpus all`. If you have no GPU, use Ubuntu:

```bash
export CLAUDE_CODE_IMAGE_TAG=latest
codefreedom claude --sandbox
```

### "Docker not found"

Install Docker from [docker.com](https://docs.docker.com/engine/install/).

## Claude Code Issues

### "Claude CLI not found"

```bash
npm install -g @anthropic-ai/claude-code
```

### How Do I Know Which Model I'm Using?

```bash
codefreedom claude --list-profiles    # See profile env vars
codefreedom proxy validate            # Check model aliases
```

Or query the proxy directly:

```bash
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

## Debugging

### See What's Loading

```bash
codefreedom claude --profile bare 2>&1 | grep -E '\[ENV\]|\[PROFILE\]'
```

Output:

```
[ENV] Loading configuration...
  [ENV] Loaded config from ~/.codefreedom/.env
[PROFILE] Loading 'pro' (inherits from 'default')...
     ANTHROPIC_BASE_URL=http://localhost:4000
     CLAUDE_MODEL=CodeFreedom/Pro
```

### Validate Everything

```bash
codefreedom proxy validate
```

Checks provider files, API keys, model aliases, and database connection.

## Web Search Not Working

Claude Code's built-in `WebSearch` often doesn't work. Use the proxy's web search interception instead:

```bash
codefreedom tools web init
codefreedom tools web start
```

Then enable web search interception in `~/.codefreedom/proxy/config/config.yaml`.

## General Questions

### Where Are My Config Files?

Everything lives in `~/.codefreedom/`:

```
~/.codefreedom/
├── profiles/              # Profile JSON files
├── proxy/                 # Proxy config
├── .env.claude            # Claude Code settings
├── .env.claude.secrets    # Claude Code secrets
├── .env.proxy             # Proxy settings
├── .env.proxy.secrets     # Proxy secrets (API keys)
├── sandbox/               # Isolated sandbox state
└── backup/                # Backup archives
```

### Can I Use Free Models?

Yes. See [OpenCode Zen](recipes/opencode-zen.md) and [NVIDIA](recipes/nvidia.md) for free options.

### How Do I Switch Models?

Edit model aliases in `~/.codefreedom/.env.proxy`:

```bash
LITELLM_MODEL_ALIAS_ULTRA="DeepSeek/DeepSeek-V4-Pro"
```

Then use `codefreedom claude --profile ultra`.

### Can I Run Without Docker?

Claude Code in local mode doesn't need Docker. The proxy requires Docker.

```bash
codefreedom claude --native-models    # Local, no proxy, no Docker
```
