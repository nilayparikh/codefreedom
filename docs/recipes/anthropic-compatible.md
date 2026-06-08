---
title: Anthropic Compatible
description: Connect any Anthropic-compatible endpoint to your proxy.
---

# Anthropic Compatible

Connect any service that speaks the Anthropic `/v1/messages` API.

## Step 1: Add the Provider

Edit `~/.codefreedom/proxy/config/providers/anthropic-compatible.yaml`:

```yaml
model_list:
  - model_name: "MyAnthropic/Model"
    anthropic_api_base: "https://your-api.example.com/v1"
    anthropic_api_key: "${YOUR_ANTHROPIC_KEY}"
```

## Step 2: Add the API Key

Edit `~/.codefreedom/.env.proxy.secrets`:

```bash
YOUR_ANTHROPIC_KEY="your-key-here"
```

## Step 3: Enable the Provider

In `~/.codefreedom/proxy/config/config.yaml`:

```yaml
include:
  - providers/anthropic-compatible.yaml
```

## Step 4: Restart

```bash
codefreedom proxy restart
```

## Use It

```bash
export LITELLM_MODEL_ALIAS_PRO="MyAnthropic/Model"
codefreedom claude --profile pro
```
