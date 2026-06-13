---
title: VSCode
description: Configure VSCode to use CodeFreedom's proxy for AI features.
---

# VSCode

Configure VSCode to use CodeFreedom's proxy for AI features.

## Quick Start

```bash
# Generate VSCode config
cf setup config vscode
# or
cf s c vscode
```

This generates `~/.codefreedom/vscode/settings.json` with proxy settings.

## How It Works

```
VSCode → localhost:4000 → LiteLLM Proxy → AI Model
```

VSCode talks to your local proxy. The proxy routes requests to whichever model you configured.

## Configuration

The generated config is at `~/.codefreedom/vscode/settings.json`:

```json
{
  "github.copilot.chat.codeGeneration.models": {
    "custom": {
      "displayName": "Qwen3.6-27B",
      "requestUrl": "http://localhost:4000/v1/chat/completions",
      "model": "custom:Qwen3.6-27B"
    }
  }
}
```

## Apply to VSCode

Copy the generated config to your VSCode settings:

```bash
cp ~/.codefreedom/vscode/settings.json ~/.config/Code/User/settings.json
```

Or use VSCode's settings UI to import the config.

## Troubleshooting

### VSCode Can't Connect

```bash
# Check proxy is running
cf run proxy status
# or
cf r px status

# Test connectivity
curl http://localhost:4000/v1/models
```
