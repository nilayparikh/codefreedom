---
title: OpenCode Zen
description: Free models via OpenCode Zen — MiMo, Nemotron, DeepSeek, MiniMax.
---

# OpenCode Zen

Multiple free models through [OpenCode Zen](https://opencode.ai/zen). No billing required.

## Models Available

| Model | Context | Notes |
|-------|---------|-------|
| MiMo-V2.5 | 1M | Vision + reasoning |
| Nemotron-3-Super | 262K | Text-only |
| Nemotron-3-Ultra | 1M | Vision |
| DeepSeek-V4-Flash | 1M | Fast inference, 384K output |
| Big-Pickle | 262K | General purpose |
| MiniMax-M3 | 512K | Vision + reasoning |

## Step 1: Get an API Key

1. Sign up at [opencode.ai/auth](https://opencode.ai/auth)
2. Copy your API key

## Step 2: Add the Key

Edit `~/.codefreedom/.env.proxy.secrets`:

```bash
OPENCODE_ZEN_API_KEY="your-key-here"
```

## Step 3: Enable Models

In `~/.codefreedom/proxy/config/config.yaml`, make sure the OpenCode Zen provider is included:

```yaml
include:
  - providers/opencode-zen.yaml
```

## Step 4: Restart

```bash
codefreedom proxy restart
```

## Use It

```bash
codefreedom claude --profile ultra    # If you mapped Ultra to an OpenCode Zen model
```

Or set a model alias in `~/.codefreedom/.env.proxy`:

```bash
LITELLM_MODEL_ALIAS_FLASH="OpenCodeZen/DeepSeek-V4-Flash-FREE"
```

## Rate Limits

Free models have quotas and rate limits. For production work, consider a paid provider.
