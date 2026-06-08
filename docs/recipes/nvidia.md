---
title: NVIDIA
description: Free serverless AI endpoints via NVIDIA — DeepSeek, GLM, Kimi, Step.
---

# NVIDIA

Free serverless endpoints through [build.nvidia.com](https://build.nvidia.com). No billing required for free endpoints.

## Models Available

| Model | Context | Notes |
|-------|---------|-------|
| DeepSeek-V4-Flash | 1M | Fast inference, 384K output |
| DeepSeek-V4-Pro | 1M | Strong reasoning |
| GLM-5.1 | 204K | Multilingual, reasoning |
| Kimi-K2.6 | 256K | Vision, thinking mode |
| Step-3.7-Flash | 262K | Vision, fast |

## Step 1: Get an API Key

1. Sign up at [build.nvidia.com](https://build.nvidia.com)
2. Get your free API key

## Step 2: Add the Key

Edit `~/.codefreedom/.env.proxy.secrets`:

```bash
NVIDIA_API_KEY="your-key-here"
```

## Step 3: Enable Models

In `~/.codefreedom/proxy/config/config.yaml`, make sure the NVIDIA provider is included:

```yaml
include:
  - providers/nvidia.yaml
```

## Step 4: Restart

```bash
codefreedom proxy restart
```

## Use It

Set a model alias in `~/.codefreedom/.env.proxy`:

```bash
LITELLM_MODEL_ALIAS_ULTRA="NVIDIA/Kimi-K2.6"
LITELLM_MODEL_ALIAS_FLASH="NVIDIA/DeepSeek-V4-Flash"
```

Then:

```bash
codefreedom claude --profile ultra    # Routes to Kimi-K2.6
codefreedom claude --profile air     # Routes to DeepSeek-V4-Flash
```

## Rate Limits

Free endpoints are subject to rate limits. Check [build.nvidia.com](https://build.nvidia.com) for current limits.
